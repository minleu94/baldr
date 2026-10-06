from decision_module.recommendation.contracts import RecommendationItem


def replay_item(source: RecommendationItem) -> RecommendationItem:
    return RecommendationItem(
        stock_code=source.stock_code,
        stock_name=source.stock_name,
        rule_score=source.rule_score,
        close_price=source.close_price,
        price_change=source.price_change,
        indicator_score=source.indicator_score,
        pattern_score=source.pattern_score,
        volume_score=source.volume_score,
        industry=source.industry,
        reason_text=source.reason_text,
    )
