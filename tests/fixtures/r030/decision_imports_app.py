from app_module.recommendation_service import RecommendationService


def build() -> RecommendationService:
    return RecommendationService()
