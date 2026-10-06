def load_saved_result(service: object, result_id: str) -> object:
    saved = service.last_recommendation_result
    return saved if saved.result_id == result_id else None
