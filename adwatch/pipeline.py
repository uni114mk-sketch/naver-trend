"""수집 → 증거 → 판정 → 지역별 정리 파이프라인."""
from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Protocol

from .config import Settings
from .db import Store
from .models import (
    MEDIUM_LABEL, STATUS_CANDIDATE, STATUS_MANUAL, STATUS_NONE, STATUS_OWN,
    Candidate, Evidence, Finding, PlaceVerdict, PostVerdict,
)
from .report.txt import write_region_txt
from .report.xlsx import write_xlsx

log = logging.getLogger("adwatch")


class Backends(Protocol):
    """실제 네이버/Claude 연동과 테스트용 가짜 구현이 공유하는 인터페이스."""
    def blog_urls(self, keyword: str, n: int) -> list[dict]: ...
    def cafe_urls(self, keyword: str, n: int) -> list[dict]: ...
    def place_ids(self, keyword: str, n: int) -> list[str]: ...
    def capture_place(self, pid: str, out_path: Path) -> dict: ...
    def collect_evidence(self, url: str, screenshot_path: Path, image_dir: Path) -> Evidence: ...
    def classify_post(self, text: str, image_paths: list[str], url: str, medium_label: str) -> PostVerdict: ...
    def classify_place(self, screenshot_path: str, place_name: str, url: str) -> PlaceVerdict: ...


class Pipeline:
    def __init__(self, settings: Settings, store: Store, backends: Backends):
        self.s = settings
        self.store = store
        self.b = backends

    # ---------- 수집 ----------
    def collect_candidates(self, region: str, keyword: str, medium: str) -> list[Candidate]:
        n = self.s.place_top_n if medium == "place" else self.s.top_n
        if medium == "blog":
            raw = self.b.blog_urls(keyword, n)
        elif medium == "cafe":
            raw = self.b.cafe_urls(keyword, n)
        elif medium == "place":
            from .collectors.place import place_url
            raw = [{"url": place_url(pid), "author": "", "title": "", "pid": pid} for pid in self.b.place_ids(keyword, n)]
        else:
            return []
        out = []
        for rank, item in enumerate(raw, 1):
            out.append(Candidate(url=item["url"], medium=medium, region=region, keyword=keyword,
                                 title=item.get("title", ""), rank=rank, author=item.get("author", ""),
                                 extra={k: v for k, v in item.items() if k not in ("url", "title", "author")}))
        return out

    def _is_own_channel(self, c: Candidate) -> bool:
        if c.medium == "blog" and c.author in self.s.own_blog_ids:
            return True
        if c.medium == "cafe" and c.author in self.s.own_cafe_ids:
            return True
        return False

    def _mentions_own_brand(self, *texts: str) -> bool:
        blob = " ".join(t for t in texts if t).replace(" ", "")
        return any(k.replace(" ", "") in blob for k in self.s.own_brand_keywords)

    # ---------- 한 건 처리 ----------
    def process(self, c: Candidate, run_date: str, run_dir: Path) -> Finding:
        region_dir = run_dir / c.region
        region_dir.mkdir(parents=True, exist_ok=True)
        label = MEDIUM_LABEL[c.medium]
        tmp_shot = region_dir / f"_tmp_{c.medium}_{abs(hash(c.url)) % 10**8}.png"
        f = Finding(url=c.url, medium=c.medium, region=c.region, keyword=c.keyword, run_date=run_date,
                    title=c.title, author=c.author)

        if self._is_own_channel(c):
            f.status, f.summary = STATUS_OWN, "자사 공식 채널"
            return f

        if c.medium == "place":
            try:
                info = self.b.capture_place(c.extra.get("pid", ""), tmp_shot)
                v = self.b.classify_place(str(tmp_shot), info.get("name", ""), c.url)
            except Exception as e:
                log.warning("플레이스 처리 실패 %s: %s", c.url, e)
                f.status, f.summary = STATUS_MANUAL, f"자동 처리 실패: {e}"
                f.violation_type = "수동 확인 필요"
                return self._finalize(f, tmp_shot, region_dir, label)
            f.clinic_name = v.clinic_name or info.get("name", "")
            f.confidence, f.summary = v.confidence, v.summary
            f.basis = v.evidence_text
            if self._mentions_own_brand(f.clinic_name):
                f.status = STATUS_OWN
            elif v.price_exposed:
                f.violation_type, f.status = "플레이스 대표 이미지 가격·이벤트 노출", STATUS_CANDIDATE
            else:
                f.violation_type, f.status = "해당없음", STATUS_NONE
            return self._finalize(f, tmp_shot, region_dir, label)

        # 블로그 / 카페
        ev = self.b.collect_evidence(c.url, tmp_shot, region_dir / "_images")
        if not ev.accessible:
            f.status, f.summary = STATUS_MANUAL, ev.note or "본문 열람 불가"
            f.violation_type = "수동 확인 필요"
            return self._finalize(f, tmp_shot, region_dir, label)
        if self._mentions_own_brand(ev.text):
            f.status, f.summary = STATUS_OWN, "본문에 자사 브랜드 언급"
            return self._finalize(f, tmp_shot, region_dir, label)
        try:
            v = self.b.classify_post(ev.text, ev.image_paths, c.url, label)
        except Exception as e:
            log.warning("판정 실패 %s: %s", c.url, e)
            f.status, f.summary = STATUS_MANUAL, f"판정 실패: {e}"
            f.violation_type = "수동 확인 필요"
            return self._finalize(f, tmp_shot, region_dir, label)
        f.clinic_name, f.author_type = v.clinic_name, v.author_type
        f.violation_type, f.confidence, f.summary = v.violation_type, v.confidence, v.summary
        f.basis = ", ".join(v.identification_basis + v.ad_signals)
        if self._mentions_own_brand(v.clinic_name):
            f.status = STATUS_OWN
        elif not v.clinic_identified and v.confidence == "낮음" and "직접 확인" in (v.summary or ""):
            f.status, f.violation_type = STATUS_MANUAL, "수동 확인 필요"
        elif v.violation_type == "해당없음" or not v.clinic_identified:
            f.status = STATUS_NONE
        else:
            f.status = STATUS_CANDIDATE
        return self._finalize(f, tmp_shot, region_dir, label)

    def _finalize(self, f: Finding, tmp_shot: Path, region_dir: Path, label: str) -> Finding:
        """신고 후보면 지역명_매체_번호.png 로 이름 확정, 아니면 _기타/ 로 이동."""
        if not tmp_shot.exists():
            return f
        if f.is_reportable:
            f.seq = self.store.next_seq(f.run_date, f.region, f.medium)
            final = region_dir / f"{f.region}_{label}_{f.seq:02d}.png"
        else:
            other = region_dir / "_기타"
            other.mkdir(exist_ok=True)
            final = other / f"{f.region}_{label}_{f.status}_{tmp_shot.stem.split('_')[-1]}.png"
        shutil.move(str(tmp_shot), str(final))
        f.screenshot = str(final)
        return f

    # ---------- 전체 실행 ----------
    def run(self, run_date: str | None = None, regions: list[str] | None = None, limit: int | None = None) -> list[Finding]:
        run_date = run_date or datetime.now().strftime("%Y-%m-%d")
        run_dir = self.s.output_dir / run_date
        run_dir.mkdir(parents=True, exist_ok=True)
        known = self.store.known_urls()
        seen_this_run: set[str] = set()
        results: list[Finding] = []
        target = {r: k for r, k in self.s.regions.items() if not regions or r in regions}

        for region, keywords in target.items():
            for keyword in keywords:
                for medium in self.s.media:
                    try:
                        cands = self.collect_candidates(region, keyword, medium)
                    except Exception as e:
                        log.error("수집 실패 %s/%s/%s: %s", region, keyword, medium, e)
                        continue
                    log.info("%s [%s/%s] %d건 수집", region, keyword, MEDIUM_LABEL[medium], len(cands))
                    for c in cands:
                        if c.url in known or c.url in seen_this_run:
                            continue
                        seen_this_run.add(c.url)
                        f = self.process(c, run_date, run_dir)
                        self.store.upsert(f)
                        results.append(f)
                        log.info("  %s → %s %s", c.url, f.status, f.clinic_name or "")
                        if limit and len(results) >= limit:
                            self.write_reports(run_date)
                            return results
        self.write_reports(run_date)
        return results

    def write_reports(self, run_date: str) -> Path:
        run_dir = self.s.output_dir / run_date
        items = self.store.by_run(run_date)
        reportable = [f for f in items if f.is_reportable]
        excluded = [f for f in items if not f.is_reportable]
        regions = sorted({f.region for f in reportable})
        for region in regions:
            write_region_txt(run_dir / region, region, run_date, [f for f in reportable if f.region == region])
        write_xlsx(run_dir / "전체.xlsx", reportable, excluded)
        return run_dir


class LiveBackends:
    """실제 네이버 + Claude 연동. with 문으로 사용 (브라우저 수명 관리)."""

    def __init__(self, settings: Settings, use_ai: bool = True):
        from .collectors.search_tab import SearchTabCollector
        self.s = settings
        self.tab = SearchTabCollector(delay_seconds=settings.delay_seconds)
        self.api = None
        if settings.naver_client_id and settings.naver_client_secret:
            from .collectors.naver_api import NaverSearchAPI
            self.api = NaverSearchAPI(settings.naver_client_id, settings.naver_client_secret)
        if not settings.use_search_tab and self.api is None:
            raise ValueError("use_search_tab=false 이면 네이버 검색 API 키가 필요합니다.")
        if use_ai and settings.anthropic_api_key:
            from .classifier import Classifier
            self.clf = Classifier(model=settings.model, effort=settings.effort, api_key=settings.anthropic_api_key)
        else:
            from .regex_classifier import RegexClassifier
            all_keywords = [k for ks in settings.regions.values() for k in ks]
            self.clf = RegexClassifier(all_keywords)
            log.info("Claude API 키 없음 또는 --no-ai: 병원명 정규식 판정만 수행")

    def __enter__(self):
        self.tab.__enter__()
        from .collectors.place import PlaceCapturer
        from .evidence import EvidenceCollector
        self.place = PlaceCapturer(self.tab.context, self.s.delay_seconds)
        self.ev = EvidenceCollector(self.tab.context, self.s.delay_seconds, self.s.max_images_per_post)
        return self

    def __exit__(self, *exc):
        self.tab.__exit__(*exc)

    def blog_urls(self, keyword, n):
        if self.s.use_search_tab:
            items = self.tab.blog(keyword, n)
            if items:
                return items
            log.warning("검색탭에서 블로그 URL 을 못 찾음 (%s). API 로 대체", keyword)
        return self.api.blog(keyword, n) if self.api else []

    def cafe_urls(self, keyword, n):
        if self.s.use_search_tab:
            items = self.tab.cafe(keyword, n)
            if items:
                return items
            log.warning("검색탭에서 카페 URL 을 못 찾음 (%s). API 로 대체", keyword)
        return self.api.cafe(keyword, n) if self.api else []

    def place_ids(self, keyword, n):
        return self.tab.place_ids(keyword, n)

    def capture_place(self, pid, out_path):
        return self.place.capture(pid, str(out_path))

    def collect_evidence(self, url, screenshot_path, image_dir):
        return self.ev.collect(url, screenshot_path, image_dir)

    def classify_post(self, text, image_paths, url, medium_label):
        return self.clf.classify_post(text, image_paths, url, medium_label)

    def classify_place(self, screenshot_path, place_name, url):
        return self.clf.classify_place(screenshot_path, place_name, url)
