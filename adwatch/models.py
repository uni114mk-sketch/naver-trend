from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

Medium = Literal["blog", "cafe", "place"]
MEDIUM_LABEL = {"blog": "블로그", "cafe": "카페", "place": "플레이스"}

# 상태 흐름: 후보 -> (사람 확인) 신고함 -> 삭제됨 / 유지됨. 자사·해당없음은 신고 대상 아님.
STATUS_CANDIDATE = "후보"
STATUS_REPORTED = "신고함"
STATUS_DELETED = "삭제됨"
STATUS_ALIVE = "유지됨"
STATUS_OWN = "자사"
STATUS_NONE = "해당없음"
STATUS_MANUAL = "수동확인"


@dataclass
class Candidate:
    """수집 단계에서 나온 URL 한 건."""
    url: str
    medium: str
    region: str
    keyword: str
    title: str = ""
    rank: int = 0
    author: str = ""          # 블로그 아이디 / 카페 아이디 / 플레이스 업체명
    extra: dict = field(default_factory=dict)


@dataclass
class Evidence:
    """게시글에서 뽑은 본문·이미지·캡처."""
    text: str = ""
    image_paths: list[str] = field(default_factory=list)
    screenshot_path: str = ""
    accessible: bool = True     # False면 로그인 필요 등으로 본문 열람 불가
    note: str = ""


class PostVerdict(BaseModel):
    """블로그·카페 게시글 판정 결과 (Claude structured output)."""
    clinic_identified: bool = Field(description="특정 병원을 식별할 수 있는가")
    clinic_name: str = Field(default="", description="식별된 병원명. 없으면 빈 문자열")
    identification_basis: list[str] = Field(
        default_factory=list,
        description="식별 근거: 병원명 텍스트 / 로고 / 간판 / 원내 인테리어 / 지도·주소 / 원장 이름 등",
    )
    author_type: Literal["병원공식", "제3자", "불명"] = Field(description="작성 주체")
    ad_signals: list[str] = Field(
        default_factory=list,
        description="광고 신호: 협찬·제공 표시, 체험단, 가격·이벤트, 전후사진, 치료경험담, 예약 유도 링크 등",
    )
    has_review_number: bool = Field(description="의료광고 심의필 번호가 기재되어 있는가")
    violation_type: Literal["비의료인 미심의 의료광고", "의료기관 미심의 광고", "해당없음"]
    confidence: Literal["높음", "중간", "낮음"]
    summary: str = Field(description="신고서에 그대로 쓸 수 있는 1~2문장 근거 요약")


class PlaceVerdict(BaseModel):
    """플레이스 대표 이미지 판정 결과."""
    price_exposed: bool = Field(description="대표 이미지에 가격·할인·이벤트 문구가 노출되는가")
    evidence_text: str = Field(default="", description="이미지에서 읽히는 가격·이벤트 문구 원문")
    clinic_name: str = Field(default="", description="플레이스 업체명")
    confidence: Literal["높음", "중간", "낮음"]
    summary: str = Field(description="신고서에 그대로 쓸 수 있는 1~2문장 근거 요약")


@dataclass
class Finding:
    """DB에 저장되는 최종 한 건."""
    url: str
    medium: str
    region: str
    keyword: str
    run_date: str
    seq: int = 0
    title: str = ""
    author: str = ""
    clinic_name: str = ""
    author_type: str = ""
    violation_type: str = ""
    confidence: str = ""
    basis: str = ""
    summary: str = ""
    screenshot: str = ""
    status: str = STATUS_CANDIDATE
    reported_at: str = ""
    result: str = ""

    @property
    def medium_label(self) -> str:
        return MEDIUM_LABEL.get(self.medium, self.medium)

    @property
    def is_reportable(self) -> bool:
        return self.status in (STATUS_CANDIDATE, STATUS_MANUAL)
