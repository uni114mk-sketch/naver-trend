"""Claude 로 게시글 / 플레이스 이미지 판정. 결과는 '후보' 이며 최종 판단은 사람이 합니다."""
from __future__ import annotations

import base64
from pathlib import Path

import anthropic

from .models import PlaceVerdict, PostVerdict

POST_SYSTEM = """당신은 한국 의료법상 의료광고 규정을 잘 아는 검토자입니다.
네이버 블로그·카페 게시글(본문 텍스트와 이미지)을 보고 아래를 판정합니다.

1. 특정 병원 식별 여부: 본문에 병원명(OO피부과, OO의원, OO클리닉), 원장 이름, 주소·지도, 또는 이미지에 로고·간판·원내 인테리어가 있어 어느 병원인지 특정 가능한가.
2. 작성 주체: 병원 공식 채널(병원 소개·공지 어투, 원장/직원 작성)인지, 제3자(체험단·인플루언서·일반인 후기)인지.
3. 광고 신호: "협찬/제공받아/체험단/원고료" 표시, 가격·이벤트, 전후사진, 치료경험담(효과 보장·추천), 예약 유도 링크·전화번호.
4. 심의필: "의료광고심의필", "심의번호", "대한의사협회 의료광고심의" 같은 기재가 있는가.

violation_type 판정 기준:
- 제3자가 특정 병원을 식별 가능하게 홍보(후기·체험단·가격 등) → "비의료인 미심의 의료광고"
- 병원 공식 채널이 심의필 없이 광고성 게시(가격·이벤트·전후사진·치료경험담) → "의료기관 미심의 광고"
- 병원이 특정되지 않거나 광고성이 없음(단순 정보, 피부 관리 팁 등) → "해당없음"

confidence: 병원 특정과 광고성이 모두 명확하면 "높음", 하나가 애매하면 "중간", 둘 다 애매하면 "낮음".
summary 는 신고서에 그대로 붙일 수 있게 사실만 1~2문장으로 씁니다. 예: "제3자 블로그가 OO피부과 원내 사진과 로고를 노출하며 레이저 시술 가격과 후기를 게시함. 심의필 기재 없음."
확실하지 않은 것을 단정하지 마세요."""

PLACE_SYSTEM = """당신은 한국 의료법상 의료광고 규정을 잘 아는 검토자입니다.
네이버 플레이스(병원) 페이지 상단 캡처를 보고, 대표 이미지(사진 영역)에 가격·할인·이벤트 문구가 노출되어 있는지 판정합니다.
- 숫자 가격(예: 9,900원, 19만원), 할인율(50%), "이벤트", "특가", "1+1" 같은 문구가 이미지 안에 있으면 price_exposed=true.
- 업체명·진료과목·주소만 있으면 false.
evidence_text 에는 읽히는 문구를 그대로 적고, summary 는 신고서에 붙일 1~2문장으로 씁니다."""


def _image_block(path: str) -> dict:
    data = base64.standard_b64encode(Path(path).read_bytes()).decode()
    media = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


class Classifier:
    def __init__(self, model: str = "claude-opus-5", effort: str = "medium", api_key: str | None = None):
        self.client = anthropic.Anthropic(api_key=api_key or None)
        self.model = model
        self.effort = effort

    def _parse(self, system: str, content: list[dict], schema):
        resp = self.client.messages.parse(
            model=self.model,
            max_tokens=4000,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_format=schema,
            output_config={"effort": self.effort},
        )
        if resp.stop_reason == "refusal":
            raise RuntimeError("모델이 판정을 거부했습니다 (refusal). 수동 확인 필요")
        return resp.parsed_output

    def classify_post(self, text: str, image_paths: list[str], url: str, medium_label: str) -> PostVerdict:
        content: list[dict] = [{"type": "text", "text": f"[{medium_label} 게시글] URL: {url}\n\n[본문]\n{text or '(본문 없음)'}"}]
        for p in image_paths:
            content.append(_image_block(p))
        if image_paths:
            content.append({"type": "text", "text": f"위 {len(image_paths)}장은 본문 이미지입니다. 로고·간판·인테리어·가격표를 확인하세요."})
        return self._parse(POST_SYSTEM, content, PostVerdict)

    def classify_place(self, screenshot_path: str, place_name: str, url: str) -> PlaceVerdict:
        content = [
            {"type": "text", "text": f"[플레이스] 업체명: {place_name or '(미상)'} URL: {url}"},
            _image_block(screenshot_path),
        ]
        return self._parse(PLACE_SYSTEM, content, PlaceVerdict)
