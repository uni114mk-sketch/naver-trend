from adwatch.regex_classifier import RegexClassifier, find_clinics


def test_find_clinics_filters_keyword_and_generic():
    t = "강남피부과 추천! 오늘은 라라피부과의원에서 피코토닝. 동네피부과 말고 여기 클리닉 좋아요. 유앤아이의원은 제외 대상 아님"
    assert find_clinics(t, ["강남피부과"]) == ["라라피부과의원", "유앤아이의원"]


def test_regex_classifier_statuses():
    c = RegexClassifier(["강남피부과"])
    v = c.classify_post("라라피부과 체험단으로 99,000원 이벤트 받았어요", [], "u", "블로그")
    assert v.clinic_identified and v.clinic_name == "라라피부과" and v.violation_type == "비의료인 미심의 의료광고" and "체험단" in v.ad_signals
    v2 = c.classify_post("피부 관리 팁 정리", [], "u", "블로그")
    assert not v2.clinic_identified and "직접 확인" in v2.summary
