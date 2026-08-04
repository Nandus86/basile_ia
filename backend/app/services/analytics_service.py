import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from app.models.user_analytics import UserAnalytics
import math

logger = logging.getLogger(__name__)

class AnalyticsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_session_id(self, session_id: str) -> Optional[UserAnalytics]:
        query = select(UserAnalytics).where(UserAnalytics.session_id == session_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    def _calculate_engagement_score(self, profile_data: dict, interaction_count: int, days_since_last: int) -> float:
        """Score 0-100, calculado deterministicamente."""
        # Frequência (40% do score)
        frequency = min(interaction_count / 50, 1.0) * 40
        
        # Recência (30% do score)
        if days_since_last <= 1:
            recency = 30
        elif days_since_last <= 7:
            recency = 30 * (1 - (days_since_last - 1) / 6)
        elif days_since_last <= 30:
            recency = 10 * (1 - (days_since_last - 7) / 23)
        else:
            recency = 0
            
        # Profundidade (20% do score)
        metrics = profile_data.get("__zona_metricas", {})
        avg_msgs = metrics.get("avg_messages_per_session", 0)
        depth = min(avg_msgs / 10, 1.0) * 20
        
        # Qualidade (10% do score)
        learned = profile_data.get("__zona_aprendizado", {})
        has_preferences = bool(learned.get("active_preferences"))
        has_corrections = bool(learned.get("active_corrections"))
        quality = 10 if (has_preferences or has_corrections) else 5
        
        return round(frequency + recency + depth + quality, 1)

    def _determine_care_priority(self, score: float, days_since_last: int) -> str:
        if score < 20 and days_since_last > 14:
            return "critical"
        elif score < 40 or days_since_last > 7:
            return "high"
        elif score >= 40 and score <= 70:
            return "medium"
        else:
            return "low"

    async def update_post_interaction(self, session_id: str, payload: dict) -> None:
        """
        Called after processing a webhook message to update the real-time counters and CRM snapshot.
        If the user has >= 3 interactions, their profile is created/updated.
        """
        try:
            # Check interaction count via JobLog to know if we should create a profile
            # Or we can just increment here. The issue is we don't track raw message count directly if it's the 1st.
            # But we can assume 1 webhook = 1 interaction.
            
            # extract church_id if available
            church_id = None
            if isinstance(payload, dict):
                church_data = payload.get("church")
                if isinstance(church_data, dict):
                    church_id = church_data.get("_id")

            analytics = await self.get_by_session_id(session_id)
            now = datetime.now(timezone.utc)

            if not analytics:
                # We could wait for 3 interactions by querying JobLog here, 
                # but to be efficient, let's just create it and increment.
                # When interaction_count >= 3 it becomes "active" for the Analyst.
                analytics = UserAnalytics(
                    session_id=session_id,
                    church_id=church_id,
                    interaction_count=1,
                    first_seen_at=now,
                    last_seen_at=now,
                    profile_data={
                        "__zona_crm": {},
                        "__zona_aprendizado": {},
                        "__zona_metricas": {}
                    }
                )
                self.db.add(analytics)
            else:
                analytics.interaction_count += 1
                analytics.last_seen_at = now
                if church_id:
                    analytics.church_id = church_id
                    
            # --- Update CRM Zone (Snapshot) ---
            # Extract standard fields to __zona_crm only if they changed (or just refresh)
            # User Q8 answer: "só em mudanças" -> We check if the new payload differs for relevant fields.
            crm_zone = analytics.profile_data.get("__zona_crm", {})
            member = payload.get("member", {})
            member_fin = payload.get("member_fin", {})
            church = payload.get("church", {})
            glob = payload.get("global", {})
            
            new_crm_data = {
                "display_name": member.get("fullname"),
                "first_name": member.get("name") or glob.get("name"),
                "phone": member.get("phone") or glob.get("phone"),
                "role": member.get("role"),
                "role_profile": member_fin.get("role_profile"),
                "church_name": church.get("church_name"),
                "preferred_language": member.get("preferredLanguage") or church.get("preferredLanguage")
            }
            
            # Remove None values
            new_crm_data = {k: v for k, v in new_crm_data.items() if v is not None}
            
            # Check for changes
            has_changes = False
            for k, v in new_crm_data.items():
                if crm_zone.get(k) != v:
                    crm_zone[k] = v
                    has_changes = True
                    
            if has_changes:
                crm_zone["_last_refresh"] = now.isoformat()
            
            analytics.profile_data["__zona_crm"] = crm_zone

            # --- Update Metrics Zone (Deterministic) ---
            metrics_zone = analytics.profile_data.get("__zona_metricas", {})
            total_sessions = metrics_zone.get("total_sessions", 0) + 1 # simplistic approach for this demo
            metrics_zone["total_sessions"] = total_sessions
            metrics_zone["last_agent_name"] = payload.get("ai_params", {}).get("name")
            
            analytics.profile_data["__zona_metricas"] = metrics_zone

            # --- Calculate Engagement & Priority ---
            days_since_last = 0
            if analytics.last_seen_at:
                days_since_last = (now - analytics.last_seen_at).days

            analytics.engagement_score = self._calculate_engagement_score(
                analytics.profile_data, 
                analytics.interaction_count, 
                days_since_last
            )
            analytics.care_priority = self._determine_care_priority(analytics.engagement_score, days_since_last)
            
            # Force SQLAlchemy to detect JSONB mutation
            # SQLAlchemy doesn't track deep mutations in JSONB unless flag_modified is used
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(analytics, "profile_data")

            await self.db.commit()
            
        except Exception as e:
            logger.error(f"[AnalyticsService] Failed to update post-interaction for {session_id}: {e}")
            await self.db.rollback()
