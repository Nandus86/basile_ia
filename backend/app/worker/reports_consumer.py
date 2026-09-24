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
            "Caso alguma igreja apresente o resumo 'Não houve movimentações significativas nesta igreja no dia de hoje.', "
            "você DEVE criar obrigatoriamente uma seção no início do relatório intitulada '⚠️ Alertas de Inatividade' listando essas igrejas "
            "para atenção imediata dos gestores e diretores."
        )
    
    # 2. Collect Data
    stats = {}
    sub_reports_texts = []
    
    if report.level == "church" and report.period_type == "daily":
        # DAILY CHURCH REPORT: Quantitative JEV Aggregation + Single Pastoral Qualitative Synthesis
        from app.models.conversation_message import ConversationMessage
        from app.models.job_log import JobLog
        from sqlalchemy import or_

        # 1. Fetch all church sessions for dispatch correlation fallback
        all_church_res = await session.execute(
            select(UserAnalytics.session_id).where(
                or_(
                    UserAnalytics.church_id == report.entity_id,
                    UserAnalytics.session_id.startswith(str(report.entity_id))
                )
            )
        )
        all_church_sessions = [type('UserObj', (), {'session_id': s}) for s in all_church_res.scalars().all()]

        # 2. Identify active sessions within [start_time, end_time]
        active_sessions_with_paths = {}

        msg_res = await session.execute(
            select(ConversationMessage.session_id, ConversationMessage.webhook_path)
            .where(
                ConversationMessage.created_at >= start_time,
                ConversationMessage.created_at <= end_time,
            )
            .distinct()
        )
        for s_id, w_path in msg_res.all():
            if s_id:
                active_sessions_with_paths.setdefault(str(s_id), set()).add(w_path or "")

        job_res = await session.execute(
            select(JobLog.session_id, JobLog.webhook_path)
            .where(
                JobLog.created_at >= start_time,
                JobLog.created_at <= end_time,
            )
            .distinct()
        )
        for s_id, w_path in job_res.all():
            if s_id:
                active_sessions_with_paths.setdefault(str(s_id), set()).add(w_path or "")

        # 3. Filter by allowed_endpoints if configured
        allowed_paths = config.allowed_endpoints if (config and config.allowed_endpoints) else []

        def _is_session_allowed(paths_set: set, allowed_list: list) -> bool:
            if not allowed_list:
                return True
            for p in paths_set:
                if not p:
                    continue
                clean_p = p.strip().strip("/").split("/")[-1].lower()
                for item in allowed_list:
                    if not item:
                        continue
                    clean_item = item.strip().strip("/").split("/")[-1].lower()
                    if clean_item == clean_p or clean_item in p.lower():
                        return True
            return False

        if allowed_paths:
            eligible_sessions = {
                s_id for s_id, paths in active_sessions_with_paths.items()
                if _is_session_allowed(paths, allowed_paths)
            }
        else:
            eligible_sessions = set(active_sessions_with_paths.keys())

        # Include users directly marked seen in this window when not restricted by endpoints
        if not allowed_paths:
            seen_res = await session.execute(
                select(UserAnalytics.session_id).where(
                    or_(
                        UserAnalytics.church_id == report.entity_id,
                        UserAnalytics.session_id.startswith(str(report.entity_id))
                    ),
                    UserAnalytics.last_seen_at >= start_time,
                    UserAnalytics.last_seen_at <= end_time
                )
            )
            for s_row in seen_res.scalars().all():
                if s_row:
                    eligible_sessions.add(str(s_row))

        if eligible_sessions:
            users_res = await session.execute(
                select(UserAnalytics).where(
                    or_(
                        UserAnalytics.church_id == report.entity_id,
                        UserAnalytics.session_id.startswith(str(report.entity_id))
                    ),
                    UserAnalytics.session_id.in_(eligible_sessions)
                )
            )
            users = users_res.scalars().all()
        else:
            users = []
        
        total_users = len(users)
        avg_score = sum(u.engagement_score for u in users) / total_users if total_users > 0 else 0
        critical_count = sum(1 for u in users if u.care_priority == "critical")
        
        # Collect auto dispatches for church (using all church sessions for fallback correlation)
        church_dispatches = await _collect_dispatch_stats(
            session, config, start_time, end_time, church_id=report.entity_id, church_users=all_church_sessions or users
        )
        total_disp_contacts = sum(d["total_contacts"] for d in church_dispatches)

        # 4 JEV Dimensions Initialization
        dim1_keys = [
            "visitante_novo", "cadastro_identificacao", "duvida_cultos", "celulas_grupos",
            "eventos_conferencias", "cursos_ensino_batismo", "financeiro_pix_dizimo",
            "informacao_institucional", "voluntariado_servir", "confirmacao_dialogo",
            "saudacao_gratidao", "pedido_oracao_cuidado", "outros_especiais"
        ]
        dim2_keys = [
            "estavel_rotina", "oracao_intercessao", "saude_enfermidade", "luto_perda",
            "crise_urgente", "crise_familiar", "afastamento_desanimo", "conflito_reclamacao"
        ]
        dim3_keys = ["membro_ativo", "visitante_novo", "em_risco_afastado"]
        dim4_keys = ["animado", "acolhido", "neutro", "duvidoso", "frustrado", "luto_triste"]

        dim1_counts = {k: 0 for k in dim1_keys}
        dim2_counts = {k: 0 for k in dim2_keys}
        dim3_counts = {k: 0 for k in dim3_keys}
        dim4_counts = {k: 0 for k in dim4_keys}
        casos_criticos_detalhe = []

        for u in users:
            crm = u.profile_data.get("__zona_crm", {}) if isinstance(u.profile_data, dict) else {}
            aprendizado = u.profile_data.get("__zona_aprendizado", {}) if isinstance(u.profile_data, dict) else {}
            raw_dims = aprendizado.get("raw_dimensions", {}) if isinstance(aprendizado, dict) else {}

            d1 = raw_dims.get("dimensao_1_tipo_atendimento") or aprendizado.get("tipo_atendimento")
            d2 = raw_dims.get("dimensao_2_criticidade_pastoral") or aprendizado.get("criticidade_pastoral")
            d3 = raw_dims.get("dimensao_3_vinculo") or aprendizado.get("status_vinculo")
            d4 = raw_dims.get("dimensao_4_sentimento") or aprendizado.get("sentimento_predominante")

            # Fallbacks para compatibilidade com registros anteriores
            if not d1:
                topicos = aprendizado.get("topicos_de_interesse") or []
                if any("pix" in str(t).lower() or "financ" in str(t).lower() for t in topicos):
                    d1 = "financeiro_pix_dizimo"
                elif any("culto" in str(t).lower() for t in topicos):
                    d1 = "duvida_cultos"
                elif any("célula" in str(t).lower() or "celula" in str(t).lower() or "gc" in str(t).lower() for t in topicos):
                    d1 = "celulas_grupos"
                elif u.interaction_count > 0:
                    d1 = "outros_especiais"
                else:
                    d1 = "saudacao_gratidao"

            if not d2:
                if u.care_priority == "critical": d2 = "crise_urgente"
                elif u.care_priority == "high": d2 = "saude_enfermidade"
                elif u.care_priority == "medium": d2 = "oracao_intercessao"
                else: d2 = "estavel_rotina"

            if not d3:
                if aprendizado.get("vinculo_igreja_ativo") is False:
                    d3 = "em_risco_afastado"
                elif u.interaction_count <= 2:
                    d3 = "visitante_novo"
                else:
                    d3 = "membro_ativo"

            if not d4:
                sent_leg = str(aprendizado.get("sentimento_predominante", "")).lower()
                if "acolhid" in sent_leg: d4 = "acolhido"
                elif "animad" in sent_leg or "alegre" in sent_leg: d4 = "animado"
                elif "frustrad" in sent_leg or "irritad" in sent_leg: d4 = "frustrado"
                elif "luto" in sent_leg or "triste" in sent_leg: d4 = "luto_triste"
                elif "duvid" in sent_leg or "incert" in sent_leg: d4 = "duvidoso"
                else: d4 = "neutro"

            dim1_counts[d1 if d1 in dim1_counts else "outros_especiais"] += 1
            dim2_counts[d2 if d2 in dim2_counts else "estavel_rotina"] += 1
            dim3_counts[d3 if d3 in dim3_counts else "membro_ativo"] += 1
            dim4_counts[d4 if d4 in dim4_counts else "neutro"] += 1

            # Coleta casos com atenção pastoral
            if d2 in ["crise_urgente", "luto_perda", "saude_enfermidade", "crise_familiar", "afastamento_desanimo"] or u.care_priority in ["critical", "high"]:
                name = crm.get("first_name") or crm.get("Nome Completo") or crm.get("name") or "Desconhecido"
                phone = crm.get("Celular") or crm.get("phone") or u.session_id
                casos_criticos_detalhe.append({
                    "membro_nome": name,
                    "session_id": u.session_id,
                    "phone": phone,
                    "criticidade": d2,
                    "resumo": aprendizado.get("pontos_de_atencao") or aprendizado.get("motivo_do_vinculo") or f"Atenção requerida: {d2.replace('_', ' ').title()}",
                    "sentimento": d4
                })

        relatorio_quantitativo = {
            "total_atendimentos": sum(dim1_counts.values()) or total_users,
            "total_membros_unicos": total_users,
            "dimensao_1_tipo_atendimento": dim1_counts,
            "dimensao_2_criticidade_pastoral": dim2_counts,
            "dimensao_3_vinculo": dim3_counts,
            "dimensao_4_sentimento": dim4_counts,
            "disparos_automaticos": church_dispatches,
            "total_disparos_automaticos": total_disp_contacts
        }

        stats = {
            "total_users": total_users,
            "avg_engagement_score": round(avg_score, 2),
            "critical_cases": critical_count,
            "relatorio_quantitativo": relatorio_quantitativo,
            "casos_criticos_detalhe": casos_criticos_detalhe,
            "disparos_automaticos": church_dispatches,
            "total_disparos_automaticos": total_disp_contacts
        }
        report.stats = stats

        if total_users == 0:
            report.report_content = "Não houve movimentações significativas nesta igreja no dia de hoje."
            return

        # Chamada Única de Síntese Qualitativa com a LLM
        church_title = report.entity_name or "Igreja Local"
        date_str = start_time.strftime("%d/%m/%Y")
        synthesis_prompt = (
            f"Você é o Supervisor Pastoral da igreja '{church_title}'.\n"
            f"Seu objetivo é gerar um relatório pastoral executivo, acolhedor, analítico e de alto nível para a liderança desta igreja referente a {date_str}.\n\n"
            f"MÉTRICAS QUANTITATIVAS CONSOLIDADAS:\n"
            f"{json.dumps(relatorio_quantitativo, ensure_ascii=False, indent=2)}\n\n"
            f"CASOS DE ATENÇÃO PASTORAL CRÍTICA DO DIA ({len(casos_criticos_detalhe)} casos):\n"
            f"{json.dumps(casos_criticos_detalhe, ensure_ascii=False, indent=2)}\n\n"
            f"Redija o relatório exclusivamente em formato Markdown profissional e humanizado com as seguintes seções:\n"
            f"1. 📊 **Visão Geral e Engajamento** (Resumo executivo do volume de atendimentos e principais demandas da comunidade)\n"
            f"2. ⚠️ **Atenção Pastoral Imediata** (Destaque nominal dos casos críticos de saúde, luto, crise ou afastamento, com orientações práticas)\n"
            f"3. 💡 **Oportunidades e Próximos Passos** (Recomendações pastorais para os líderes de células, voluntários e novos visitantes)\n"
            f"4. 📢 **Comunicações e Disparos** (Avaliação do impacto das mensagens e campanhas automáticas enviadas pela igreja)"
        )

        final_resp = await llm.ainvoke([
            SystemMessage(content=sys_prompt),
            HumanMessage(content=synthesis_prompt)
        ])
        report.report_content = final_resp.content
        return
            
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
            report.report_content = "Não houve movimentações significativas nesta igreja no dia de hoje."
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
                                stats_dict = report.stats or {}
                                relatorio_quant = stats_dict.get("relatorio_quantitativo") or {}
                                casos_criticos = stats_dict.get("casos_criticos_detalhe") or []
                                payload_out = {
                                    "report_id": str(report.id),
                                    "church_id": report.entity_id,
                                    "church_name": report.entity_name,
                                    "level": report.level,
                                    "period_type": report.period_type,
                                    "period_start": report.period_start.isoformat() if report.period_start else None,
                                    "period_end": report.period_end.isoformat() if report.period_end else None,
                                    "relatorio_quantitativo": relatorio_quant,
                                    "relatorio_qualitativo": report.report_content,
                                    "casos_criticos_detalhe": casos_criticos,
                                    "stats": stats_dict,
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
