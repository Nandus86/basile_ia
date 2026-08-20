import asyncio
import json
import logging
import aio_pika
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func, cast, String
from sqlalchemy.orm.attributes import flag_modified

from app.services.rabbitmq_service import rabbitmq_client
from app.database import async_session_maker
from app.models.user_analytics import UserAnalytics
from app.models.analytics_report import AnalyticsReport
from app.models.analytics_config import AnalyticsConfig
from app.models.agent import Agent

from langchain_core.messages import SystemMessage, HumanMessage

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50

from app.models.dispatcher_webhook_log import DispatcherWebhookLog

def _normalize_path(p: str) -> str:
    if not p:
        return ""
    p = p.strip().strip("/")
    for prefix in ["api/v1/trigger/personalizado/", "trigger/personalizado/", "api/v1/", "webhook/"]:
        if p.startswith(prefix):
            p = p[len(prefix):]
    return p

async def _collect_dispatch_stats(session, config, start_time, end_time, church_id: str = None, church_users: list = None) -> list:
    """
    Coleta estatísticas de disparos automáticos com base no auto_dispatch_mapping do config.
    Retorna lista com métricas detalhadas por regra mapeada.
    """
    mapping = config.auto_dispatch_mapping if config and config.auto_dispatch_mapping else []
    if not mapping:
        return []

    log_query = select(DispatcherWebhookLog).where(
        DispatcherWebhookLog.created_at >= start_time,
        DispatcherWebhookLog.created_at <= end_time
    )
    logs_res = await session.execute(log_query)
    logs = logs_res.scalars().all()
    if not logs:
        return []

    church_session_set = set()
    if church_users:
        for u in church_users:
            if u.session_id:
                church_session_set.add(str(u.session_id))

    dispatch_stats = []

    for rule in mapping:
        rule_path = (rule.get("path") or "").strip()
        rule_type_id = (rule.get("type_id") or "").strip()
        rule_label = rule.get("label") or f"{rule_path} ({rule_type_id})"

        if not rule_path and not rule_type_id:
            continue

        norm_rule_path = _normalize_path(rule_path)
        matched_batches = 0
        total_contacts = 0

        for log in logs:
            norm_log_path = _normalize_path(log.webhook_path)
            if norm_rule_path and norm_rule_path != norm_log_path and rule_path != log.webhook_path:
                continue

            payload = log.request_payload or {}
            log_type_id = payload.get("type_id") or ""
            if rule_type_id and str(rule_type_id).strip() != str(log_type_id).strip():
                continue

            if church_id:
                p_church_id = (
                    payload.get("church_id") or 
                    (payload.get("church", {}).get("_id") if isinstance(payload.get("church"), dict) else None) or
                    (payload.get("context_data", {}).get("church_id") if isinstance(payload.get("context_data"), dict) else None) or
                    (payload.get("context_data", {}).get("church", {}).get("_id") if isinstance(payload.get("context_data"), dict) and isinstance(payload.get("context_data", {}).get("church"), dict) else None)
                )
                if p_church_id:
                    if str(p_church_id) != str(church_id):
                        continue
                elif church_session_set:
                    queue_id = payload.get("queue_id", "")
                    contacts = payload.get("contacts", [])
                    matches_church = False
                    for c in contacts:
                        c_num = c.get("number") or c.get("phone") or ""
                        if c_num and (f"{queue_id}{c_num}" in church_session_set or c_num in church_session_set):
                            matches_church = True
                            break
                    if not matches_church and queue_id:
                        if any(s.startswith(str(queue_id)) for s in church_session_set):
                            matches_church = True

                    if not matches_church:
                        continue

            matched_batches += 1
            count = log.contact_count if log.contact_count is not None else len(payload.get("contacts", []))
            total_contacts += count

        if matched_batches > 0 or total_contacts > 0:
            dispatch_stats.append({
                "label": rule_label,
                "path": rule_path,
                "type_id": rule_type_id,
                "total_dispatches": matched_batches,
                "total_contacts": total_contacts
            })

    return dispatch_stats

async def process_map_reduce(session, report, config):
    """Executes the Map-Reduce logic for generating the report."""
    
    start_time = report.period_start
    end_time = report.period_end
    
    # 1. Determine Agent ID
    agent_id_to_use = None
    if report.level == "church":
        agent_id_to_use = config.church_agent_id
    elif report.level == "system":
        agent_id_to_use = config.system_agent_id
        
    if not agent_id_to_use:
        raise ValueError(f"Nenhum agente configurado para o nível '{report.level}'. Configure em AnalyticsConfig.")
        
    import uuid as uuid_mod
    try:
        agent_uuid = uuid_mod.UUID(str(agent_id_to_use))
        agent_res = await session.execute(select(Agent).where(Agent.id == agent_uuid))
    except Exception:
        agent_res = await session.execute(select(Agent).where(Agent.id == agent_id_to_use))
    agent = agent_res.scalar_one_or_none()
    if not agent:
        raise ValueError(f"Agente {agent_id_to_use} não encontrado.")
        
    from app.orchestrator.agent_factory import AgentFactory
    factory = AgentFactory(session)
    agent_config = await factory.get_agent_config(agent)
    llm = factory.create_llm(agent_config)
    sys_prompt = agent.system_prompt or "Você é um supervisor encarregado de gerar relatórios executivos baseados em sub-relatórios."
    if report.level == "system":
        sys_prompt += (
            "\n\n## ⚠️ Alertas de Inatividade\n"
            "Caso alguma igreja apresente o resumo 'Não houveram movimentações significativas nesta igreja no dia de hoje.', "
            "você DEVE criar obrigatoriamente uma seção no início do relatório intitulada '⚠️ Alertas de Inatividade' listando essas igrejas "
            "para atenção imediata dos gestores e diretores."
        )
    
    # 2. Collect Data
    stats = {}
    sub_reports_texts = []
    
    if report.level == "church" and report.period_type == "daily":
        # DAILY CHURCH REPORT: Map-Reduce over UserAnalytics
        users_res = await session.execute(
            select(UserAnalytics).where(UserAnalytics.church_id == report.entity_id)
        )
        users = users_res.scalars().all()
        
        # Calculate stats
        total_users = len(users)
        avg_score = sum(u.engagement_score for u in users) / total_users if total_users > 0 else 0
        critical_count = sum(1 for u in users if u.care_priority == "critical")
        
        # Collect auto dispatches for church
        church_dispatches = await _collect_dispatch_stats(
            session, config, start_time, end_time, church_id=report.entity_id, church_users=users
        )
        total_disp_contacts = sum(d["total_contacts"] for d in church_dispatches)

        stats = {
            "total_users": total_users,
            "avg_engagement_score": round(avg_score, 2),
            "critical_cases": critical_count,
            "disparos_automaticos": church_dispatches,
            "total_disparos_automaticos": total_disp_contacts
        }
        
        # Map phase: split into blocks
        blocks = [users[i:i + CHUNK_SIZE] for i in range(0, total_users, CHUNK_SIZE)]
        logger.info(f"[ReportsConsumer] Mapping {len(blocks)} blocks for church {report.entity_id}")
        
        for i, block in enumerate(blocks):
            block_data = []
            for u in block:
                crm = u.profile_data.get("__zona_crm", {})
                aprendizado = u.profile_data.get("__zona_aprendizado", {})
                name = crm.get("first_name") or crm.get("Nome Completo") or "Desconhecido"
                if not aprendizado: continue # skip empty
                
                block_data.append({
                    "nome": name,
                    "score": u.engagement_score,
                    "prioridade": u.care_priority,
                    "analise": aprendizado
                })
                
            if not block_data: continue
                
            map_prompt = (
                f"Resuma as tendências, problemas e vitórias deste grupo de {len(block_data)} membros "
                f"da igreja. Seja clínico e direto. Dados:\n{json.dumps(block_data, ensure_ascii=False)}"
            )
            map_resp = await llm.ainvoke([
                SystemMessage(content="Você é um assistente que sumariza perfil de membros de igreja."),
                HumanMessage(content=map_prompt)
            ])
            sub_reports_texts.append(f"--- Bloco {i+1} ---\n{map_resp.content}")

        if church_dispatches:
            disp_lines = [f"- {d['label']} (Path: {d['path']}, Type ID: {d['type_id']}): {d['total_contacts']} membros atingidos em {d['total_dispatches']} disparos" for d in church_dispatches]
            sub_reports_texts.append(
                f"--- Disparos Automáticos Realizados no Período ---\n" + "\n".join(disp_lines) + f"\nTotal de membros impactados via automação: {total_disp_contacts}"
            )
            
    elif report.period_type in ["weekly", "monthly"]:
        # WEEKLY/MONTHLY REPORT: Reduce over previous period reports
        prev_period_type = "daily" if report.period_type == "weekly" else "weekly"
        
        query = select(AnalyticsReport).where(
            AnalyticsReport.level == report.level,
            AnalyticsReport.period_type == prev_period_type,
            AnalyticsReport.entity_id == report.entity_id,
            AnalyticsReport.period_start >= start_time,
            AnalyticsReport.period_end <= end_time,
            AnalyticsReport.status == "completed"
        )
        prev_reports_res = await session.execute(query)
        prev_reports = prev_reports_res.scalars().all()
        
        if not prev_reports:
            logger.warning(f"[ReportsConsumer] Sem dados anteriores para o período {start_time} - {end_time}")
            
        all_disp_map = {}
        total_disp_period = 0
        for r in prev_reports:
            r_stats = r.stats or {}
            for d in r_stats.get("disparos_automaticos", []):
                key = (d.get("path"), d.get("type_id"))
                if key not in all_disp_map:
                    all_disp_map[key] = {
                        "label": d.get("label"),
                        "path": d.get("path"),
                        "type_id": d.get("type_id"),
                        "total_dispatches": 0,
                        "total_contacts": 0
                    }
                all_disp_map[key]["total_dispatches"] += d.get("total_dispatches", 0)
                all_disp_map[key]["total_contacts"] += d.get("total_contacts", 0)
            total_disp_period += r_stats.get("total_disparos_automaticos", 0)

        stats = {
            "total_sub_reports_processed": len(prev_reports),
            "disparos_automaticos": list(all_disp_map.values()),
            "total_disparos_automaticos": total_disp_period
        }
        
        for r in prev_reports:
            sub_reports_texts.append(
                f"--- Período {r.period_start.strftime('%d/%m')} a {r.period_end.strftime('%d/%m')} ---\n"
                f"Estatísticas: {json.dumps(r.stats)}\nResumo: {r.report_content}"
            )
            
    elif report.level == "system" and report.period_type == "daily":
        # SYSTEM DAILY REPORT: Reduce over all Church Daily Reports for that day
        target_date = start_time.date() if hasattr(start_time, 'date') else start_time
        query = select(AnalyticsReport).where(
            AnalyticsReport.level == "church",
            AnalyticsReport.period_type == "daily",
            func.date(AnalyticsReport.period_start) == target_date,
            AnalyticsReport.status == "completed"
        )
        churches_res = await session.execute(query)
        church_reports = churches_res.scalars().all()
        
        # Collect auto dispatches system-wide
        sys_dispatches = await _collect_dispatch_stats(
            session, config, start_time, end_time, church_id=None
        )
        total_sys_disp = sum(d["total_contacts"] for d in sys_dispatches)

        stats = {
            "total_churches_processed": len(church_reports),
            "disparos_automaticos": sys_dispatches,
            "total_disparos_automaticos": total_sys_disp
        }
        
        for r in church_reports:
            sub_reports_texts.append(
                f"--- Igreja: {r.entity_name} ---\n"
                f"Estatísticas: {json.dumps(r.stats)}\nResumo: {r.report_content}"
            )

        if sys_dispatches:
            disp_lines = [f"- {d['label']} (Path: {d['path']}, Type ID: {d['type_id']}): {d['total_contacts']} membros atingidos em {d['total_dispatches']} disparos" for d in sys_dispatches]
            sub_reports_texts.append(
                f"--- Disparos Automáticos Globais do Sistema ---\n" + "\n".join(disp_lines) + f"\nTotal de membros impactados via automação global: {total_sys_disp}"
            )

    # 3. Reduce Phase (Final Generation)
    report.stats = stats
    report.sub_reports = sub_reports_texts
    
    if not sub_reports_texts:
        if report.level == "church":
            report.report_content = "Não houveram movimentações significativas nesta igreja no dia de hoje."
        else:
            report.report_content = "Não houve interações ou dados suficientes neste período para gerar um relatório."
        return

    context = (
        f"Gere um relatório final consolidado para o nível '{report.level}' e período '{report.period_type}'.\n\n"
        f"ESTATÍSTICAS TOTAIS:\n{json.dumps(stats, ensure_ascii=False, indent=2)}\n\n"
        f"SUB-RELATÓRIOS DO PERÍODO:\n" + "\n\n".join(sub_reports_texts)
    )
    
    final_resp = await llm.ainvoke([
        SystemMessage(content=sys_prompt),
        HumanMessage(content=context)
    ])
    
    report.report_content = final_resp.content

async def process_report_message(message: aio_pika.abc.AbstractIncomingMessage):
    """Callback for processing analytics reports tasks."""
    async with message.process():
        try:
            body_str = message.body.decode('utf-8')
            payload = json.loads(body_str)
            report_id = payload.get("report_id")

            if not report_id:
                logger.error(f"[ReportsConsumer] Invalid payload: {payload}")
                return

            logger.info(f"[ReportsConsumer] Processing report {report_id}")

            async with async_session_maker() as session:
                # 1. Get the Report
                import uuid as uuid_mod
                try:
                    rep_uuid = uuid_mod.UUID(str(report_id))
                    report_res = await session.execute(select(AnalyticsReport).where(AnalyticsReport.id == rep_uuid))
                except Exception:
                    report_res = await session.execute(select(AnalyticsReport).where(AnalyticsReport.id == report_id))
                report = report_res.scalar_one_or_none()
                if not report:
                    logger.error(f"[ReportsConsumer] Report {report_id} not found.")
                    return
                
                # 2. Get Config
                config_res = await session.execute(select(AnalyticsConfig).limit(1))
                config = config_res.scalar_one_or_none()
                if not config:
                    logger.error("[ReportsConsumer] AnalyticsConfig not found.")
                    return

                report.status = "processing"
                await session.commit()
                
                try:
                    # RUN MAP-REDUCE
                    await process_map_reduce(session, report, config)
                    
                    report.status = "completed"
                    report.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.info(f"[ReportsConsumer] Successfully generated report {report_id}")
                    
                    # Fire webhook if configured
                    webhook_url = config.church_webhook_url if report.level == "church" else config.system_webhook_url
                    if webhook_url:
                        try:
                            import httpx
                            async with httpx.AsyncClient() as client:
                                payload_out = {
                                    "report_id": str(report.id),
                                    "level": report.level,
                                    "entity_id": report.entity_id,
                                    "period_type": report.period_type,
                                    "period_start": report.period_start.isoformat() if report.period_start else None,
                                    "period_end": report.period_end.isoformat() if report.period_end else None,
                                    "stats": report.stats,
                                    "report_content": report.report_content
                                }
                                await client.post(webhook_url, json=payload_out, timeout=10.0)
                                logger.info(f"[ReportsConsumer] Fired {report.level} webhook to {webhook_url}")
                        except Exception as e:
                            logger.error(f"[ReportsConsumer] Failed to fire {report.level} webhook: {e}")
                    
                except Exception as ex:
                    logger.error(f"[ReportsConsumer] Error running LLM for {report_id}: {ex}")
                    report.status = "failed"
                    report.error_message = str(ex)
                    report.completed_at = datetime.now(timezone.utc)
                    await session.commit()
                    
        except Exception as e:
            logger.error(f"[ReportsConsumer] Failed to process message: {e}")

async def start_reports_consumer():
    """Start listening to analytics reports queue."""
    logger.info("Starting RabbitMQ consumer for Analytics Reports...")
    await rabbitmq_client.connect()
    
    channel = rabbitmq_client.channel
    if not channel:
        logger.error("[ReportsConsumer] Failed to connect to RabbitMQ channel")
        return
        
    queue = await channel.declare_queue("analytics_reports_queue", durable=True)
    await queue.consume(process_report_message)
    
    logger.info("[ReportsConsumer] Listening for analytics_reports_queue...")
    
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        logger.info("Reports consumer cancelled.")
