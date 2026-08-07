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
        
    agent_res = await session.execute(select(Agent).where(Agent.id == agent_id_to_use))
    agent = agent_res.scalar_one_or_none()
    if not agent:
        raise ValueError(f"Agente {agent_id_to_use} não encontrado.")
        
    from app.orchestrator.agent_factory import AgentFactory
    factory = AgentFactory(session)
    agent_config = await factory.get_agent_config(agent)
    llm = factory.create_llm(agent_config)
    sys_prompt = agent.system_prompt or "Você é um supervisor encarregado de gerar relatórios executivos baseados em sub-relatórios."
    
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
        
        stats = {
            "total_users": total_users,
            "avg_engagement_score": round(avg_score, 2),
            "critical_cases": critical_count
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
            
        stats = {
            "total_sub_reports_processed": len(prev_reports)
        }
        
        for r in prev_reports:
            sub_reports_texts.append(
                f"--- Período {r.period_start.strftime('%d/%m')} a {r.period_end.strftime('%d/%m')} ---\n"
                f"Estatísticas: {json.dumps(r.stats)}\nResumo: {r.report_content}"
            )
            
    elif report.level == "system" and report.period_type == "daily":
        # SYSTEM DAILY REPORT: Reduce over all Church Daily Reports for that day
        query = select(AnalyticsReport).where(
            AnalyticsReport.level == "church",
            AnalyticsReport.period_type == "daily",
            AnalyticsReport.period_start == start_time,
            AnalyticsReport.status == "completed"
        )
        churches_res = await session.execute(query)
        church_reports = churches_res.scalars().all()
        
        stats = {
            "total_churches_processed": len(church_reports)
        }
        
        for r in church_reports:
            sub_reports_texts.append(
                f"--- Igreja: {r.entity_name} ---\n"
                f"Estatísticas: {json.dumps(r.stats)}\nResumo: {r.report_content}"
            )

    # 3. Reduce Phase (Final Generation)
    report.stats = stats
    report.sub_reports = sub_reports_texts
    
    if not sub_reports_texts:
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
