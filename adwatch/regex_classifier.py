"""Claude API 없이 쓰는 판정기. 본문 텍스트에서 병원명만 뽑아 '후보/수동확인' 을 나눈다.
최종 판단은 사람(또는 채팅의 Claude)이 본문·캡처를 보고 한다."""
from __future__ import annotations

import re

from .models import PlaceVerdict, PostVerdict

CLINIC_RE = re.compile(r"([가-힣A-Za-z0-9&·]{2,14}(?:피부과의원|피부과|의원|클리닉|성형외과|메디컬))")
STOP_PREFIX = re.compile(r"^(동네|근처|추천|유명|좋은|괜찮은|저렴한|싼|가까운|인근|여기|우리|이|그|저|어느|어떤)")
AD_SIGNALS = ["협찬", "제공받", "체험단", "원고료", "이벤트", "할인", "원 ", "만원", "예약", "전후", "비포", "애프터", "후기"]
OFFICIAL_HINTS = ["원장", "저희 병원", "본원", "내원", "진료시간", "진료 안내", "상담 문의"]


def find_clinics(text: str, exclude_keywords: list[str]) -> list[str]:
    out: list[str] = []
    for m in CLINIC_RE.finditer(text or ""):
        name = m.group(1)
        if name in exclude_keywords or STOP_PREFIX.match(name) or re.fullmatch(r"(피부과|의원|클리닉|성형외과|메디컬)", name):
            continue
        if name not in out:
            out.append(name)
    return out


class RegexClassifier:
    def __init__(self, exclude_keywords: list[str]):
        self.exclude = exclude_keywords

    def classify_post(self, text: str, image_paths: list[str], url: str, medium_label: str) -> PostVerdict:
        clinics = find_clinics(text, self.exclude)
        signals = [s.strip() for s in AD_SIGNALS if s in (text or "")]
        official = any(h in (text or "") for h in OFFICIAL_HINTS)
        has_review = bool(re.search(r"심의\s*(필|번호)|의료광고\s*심의", text or ""))
        if not clinics:
            return PostVerdict(clinic_identified=False, author_type="불명", ad_signals=signals, has_review_number=has_review,
                               violation_type="해당없음", confidence="낮음", summary="본문에서 병원명을 찾지 못함. 이미지·본문 직접 확인 필요")
        vt = "의료기관 미심의 광고" if official else "비의료인 미심의 의료광고"
        return PostVerdict(clinic_identified=True, clinic_name=clinics[0], identification_basis=["병원명 텍스트"] + (["병원명 복수: " + ", ".join(clinics[1:4])] if len(clinics) > 1 else []),
                           author_type="병원공식" if official else "제3자", ad_signals=signals, has_review_number=has_review,
                           violation_type=vt, confidence="중간" if signals else "낮음",
                           summary=f"본문에 '{clinics[0]}' 언급" + (f", 광고 신호: {', '.join(signals[:4])}" if signals else "") + ". 사람이 본문·이미지 확인 필요")

    def classify_place(self, screenshot_path: str, place_name: str, url: str) -> PlaceVerdict:
        return PlaceVerdict(price_exposed=True, evidence_text="", clinic_name=place_name, confidence="낮음",
                            summary="대표 이미지 가격 노출 여부는 캡처를 직접 확인")
