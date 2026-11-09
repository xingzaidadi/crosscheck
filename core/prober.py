"""
摸底探针(摸底建模器的抓取组件)。

输入:一个页面 URL。工具自己打开页面、拦截 XHR/fetch,抓到真实的接口请求与返回,
落盘成 capture 样本。请求体和响应 JSON 由工具获取,不需要人工提供 —— 这是本工具
区别于"人工抓包"的根本:人只给 URL。

两种模式:
  - auto   : 打开页面(可选点一下检索触发按钮),自动捕获匹配的接口流量。
  - record : 有头浏览器,人在页面上做一次检索,工具在旁录制(录制一次,之后回放)。

登录态:storageState 存文件复用;首次无 Session 则在 record 模式下人工登录一次并保存。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class Capture:
    """一次捕获到的接口调用。"""
    url: str
    method: str
    resource_type: str
    request_body: Any = None          # 解析后的请求体(JSON)或原始串
    query_params: dict[str, str] = field(default_factory=dict)
    status: int | None = None
    response_json: Any = None
    ts: float = field(default_factory=time.time)


class Prober:
    def __init__(
        self,
        url_pattern: str = "",          # 只捕获 url 含该子串的接口;空=全部 xhr/fetch
        session_file: str | None = None,
        headless: bool = True,
        video_dir: str | None = None,   # 给了就全程录视频(webm)
        artifacts_dir: str | None = None,  # 给了就在关键步骤截图
        launch_mode: str = "isolated",  # isolated(现状/CI) | persistent(真Chrome+持久profile) | existing(连已开浏览器)
        user_data_dir: str | None = None,  # persistent 模式的 profile 目录
        cdp_endpoint: str | None = None,   # existing 模式:连已开浏览器的 CDP 地址
        channel: str = "chrome",         # persistent 模式优先用真 Chrome;装不上自动退回 Chromium
    ):
        self.url_pattern = url_pattern
        self.session_file = session_file
        self.headless = headless
        self.video_dir = video_dir
        self.artifacts_dir = artifacts_dir
        self.launch_mode = launch_mode
        self.user_data_dir = user_data_dir
        self.cdp_endpoint = cdp_endpoint
        self.channel = channel
        self.captures: list[Capture] = []
        self.video_path: str | None = None
        self.screenshots: list[dict] = []   # [{name, path}]
        self.rendered_rows: list[dict] = []  # DOM 实际显示的行(UI 渲染校验用)
        self.replay_results: list[dict] = []  # 语义动作回放每步结果(UI 写入用)
        self.field_check: tuple | None = None  # (ok, 报告层):字段联动/只读校验结果
        self.value_reads: dict[str, str] = {}  # {选择器: 页面文本}:页签/按钮计算值校验用
        self.validation_errors: list[str] = []  # 回放后页面的前端校验报错文本(前端校验类用例用)

    # ───────────────────────── 抓取 ─────────────────────────

    # 安全录制(capture_only)默认放行的只读路径子串:命中则不拦(只拦真正的写/动作调用)
    _READ_OK_DEFAULT = ("/page", "/detail", "/list", "/query", "/tree", "/options",
                         "/enum", "/count", "/export", "/get", "/search")

    def probe(
        self,
        page_url: str,
        trigger_selector: str | None = None,
        wait_ms: int = 4000,
        record: bool = False,
        actions: list[dict] | None = None,
        extract: dict | None = None,
        replay_actions: list[dict] | None = None,
        field_asserts: list[dict] | None = None,
        value_selectors: list[str] | None = None,
        capture_only: bool = False,
        read_ok: tuple | None = None,
    ) -> list[Capture]:
        """
        打开 page_url,拦截流量,可选录视频/截图/跑声明式检索动作。
        - actions 给定:按声明式步骤驱动页面(选下拉/填输入、点查询…),并在 screenshot 步骤截图。
        - trigger_selector:简单情形,点一下触发检索。
        - record=True + 交互式终端:人工操作一次。
        - capture_only=True:安全录报文模式——拦截写/动作 POST,记下 method/url/body 后 abort,
          请求不落服务端(零数据变更)。用于补"动作接口只有被点过才出现报文"的空白,触发它不执行它。
          read_ok 覆盖默认放行子串(只读接口照常放行,不拦)。
        """
        from playwright.sync_api import sync_playwright  # 延迟导入,未装不影响其他模块

        shot_idx = {"n": 0}

        with sync_playwright() as p:
            context, browser, page, owns_context = self._open(p, record)

            if capture_only:
                # 安全录模式:只认被拦截+abort 的写/动作调用为捕获源;不挂 _on_response,
                # 否则执行掉的只读查询(含 POST 分页)会被 pick_write_call 误当成"写"而假阳。
                self._install_capture_only(context, read_ok)
            else:
                context.on("response", self._on_response)

            def shot(name: str) -> None:
                if not self.artifacts_dir:
                    return
                Path(self.artifacts_dir).mkdir(parents=True, exist_ok=True)
                shot_idx["n"] += 1
                stem = f"{shot_idx['n']:02d}_{name}"
                path = str(Path(self.artifacts_dir) / f"{stem}.png")
                try:
                    page.screenshot(path=path, full_page=False)
                    self.screenshots.append({"name": name, "path": path})
                except Exception as e:  # noqa: BLE001
                    print(f"  截图失败({name}): {e}")
                # 同时存 DOM,供首跑时认检索栏控件(筛选下拉、查询按钮)的选择器
                try:
                    (Path(self.artifacts_dir) / f"{stem}.html").write_text(
                        page.content(), encoding="utf-8")
                except Exception:  # noqa: BLE001
                    pass

            # 重型 SPA(含 hash 路由)用 networkidle 更可靠;超时则退回 domcontentloaded
            try:
                page.goto(page_url, wait_until="networkidle", timeout=30000)
            except Exception:  # noqa: BLE001
                page.goto(page_url, wait_until="domcontentloaded")
            page.wait_for_timeout(1500)
            shot("loaded")

            if replay_actions:
                # UI 写入:语义动作回放(含复杂控件 + 选择器自愈),抓包/录像照常
                from core.ui_actions import replay as _replay
                try:
                    self.replay_results = _replay(page, replay_actions)
                except Exception as e:  # noqa: BLE001
                    print(f"  语义回放中断: {e}")
                page.wait_for_timeout(wait_ms)
                shot("after_replay")
                # 就地验字段(联动带出值 / 只读态)—— 页面还活着才能读
                if field_asserts:
                    from core.ui_field import check_fields
                    try:
                        self.field_check = check_fields(page, field_asserts)
                    except Exception as e:  # noqa: BLE001
                        self.field_check = (False, {"name": "UI 字段校验", "ok": False, "note": str(e)[:120]})
                # 读前端校验报错(前端校验类用例:填非法值后页面报错)
                try:
                    from core.discovery.fields import read_validation_errors
                    self.validation_errors = read_validation_errors(page)
                except Exception:  # noqa: BLE001
                    self.validation_errors = []
            elif actions:
                from core.login import _run_steps
                try:
                    _run_steps(page, actions, None, shot=shot)
                except Exception as e:  # noqa: BLE001
                    print(f"  检索动作执行中断(选择器可能需调整): {e}")
                page.wait_for_timeout(wait_ms)
                shot("after_search")
            elif record:
                import sys as _sys
                if _sys.stdin and _sys.stdin.isatty():
                    print("【录制模式】在浏览器里完成一次检索,完成后回终端按回车…")
                    try:
                        input()
                    except EOFError:
                        page.wait_for_timeout(wait_ms)
                else:
                    print(f"【录制模式】非交互环境:给你 {wait_ms}ms 操作窗口后收尾…")
                    page.wait_for_timeout(wait_ms)
                shot("after_search")
            else:
                if trigger_selector:
                    try:
                        page.click(trigger_selector, timeout=5000)
                    except Exception as e:  # noqa: BLE001
                        print(f"  触发检索点击失败(选择器可能失效): {e}")
                page.wait_for_timeout(wait_ms)
                shot("after_search")

            # UI 渲染校验:读 DOM 里"实际显示"的值。两种模式:
            #   rows   —— 表格:rows_selector + columns{field:cell选择器} → 每行一条
            #   fields —— 详情:fields{container,label,value} → 标签→值 一条(label-value 页)
            if extract:
                try:
                    if "fields" in extract:
                        # 标签-值 页(descriptions/表单):全页标签序列与值序列按文档顺序 zip 配对,
                        # 不要求两者同父节点(HiUI 表格式 descriptions 标签值分处不同行)
                        self.rendered_rows = page.evaluate(
                            """(spec) => {
                              const labs=[...document.querySelectorAll(spec.label)].map(e=>(e.innerText||'').trim());
                              const vals=[...document.querySelectorAll(spec.value)].map(e=>(e.innerText||'').trim());
                              const out={}; const n=Math.min(labs.length, vals.length);
                              for(let i=0;i<n;i++){ if(labs[i] && !(labs[i] in out)) out[labs[i]]=vals[i]; }
                              return [out];
                            }""", extract["fields"])
                    else:
                        self.rendered_rows = page.evaluate(
                            """(spec) => {
                              const rows = Array.from(document.querySelectorAll(spec.rows_selector));
                              return rows.map(r => {
                                const o = {};
                                for (const k in spec.columns) {
                                  const sel = spec.columns[k];
                                  const el = sel ? r.querySelector(sel) : r;
                                  o[k] = el ? (el.innerText || '').trim() : null;
                                }
                                return o;
                              });
                            }""", extract)
                    shot("rendered")
                except Exception as e:  # noqa: BLE001
                    print(f"  DOM 抽取失败(检查 extract 规则): {e}")

            # 读指定选择器的页面文本(页签/按钮上的计数等),供"页面值↔库"校验(页面还活着)
            for sel in (value_selectors or []):
                try:
                    loc = page.locator(sel).first
                    self.value_reads[sel] = (loc.inner_text() or "").strip() if loc.count() else ""
                except Exception:  # noqa: BLE001
                    self.value_reads[sel] = ""

            # 保存/更新 Session 供回放复用(只在自己拥有的 context 上存;existing 模式是用户的真浏览器,不碰)
            if self.session_file and owns_context:
                try:
                    Path(self.session_file).parent.mkdir(parents=True, exist_ok=True)
                    context.storage_state(path=self.session_file)
                except Exception:  # noqa: BLE001
                    pass

            # 视频路径需在 close 前取句柄,close 后文件才落盘
            if self.video_dir:
                try:
                    self.video_path = page.video.path()
                except Exception:  # noqa: BLE001
                    self.video_path = None

            if owns_context:
                context.close()   # ← 视频在这里写盘
            if browser is not None:
                browser.close()   # existing 模式:断开连接,不杀用户的浏览器
        return self.captures

    # ───────────────────────── 开浏览器(三种模式) ─────────────────────────

    def _open(self, p, record: bool):
        """
        返回 (context, browser_or_None, page, owns_context)。
          isolated   : 拉 bundled Chromium + 全新 context(现状;测试/CI)。
          persistent : 真 Chrome(channel=chrome,装不上退回 Chromium)+ 持久 profile 目录,
                       登录态/缓存跨次保留;没开浏览器也能稳。首跑若有 .auth 文件则注入 cookie 引种。
          existing   : connect_over_cdp 连已开浏览器,用其现有 context(不存盘、不关它)。
        """
        headless_eff = self.headless and not record
        viewport = {"width": 1440, "height": 900}
        rec: dict[str, Any] = {}
        if self.video_dir:
            Path(self.video_dir).mkdir(parents=True, exist_ok=True)
            rec = {"record_video_dir": self.video_dir, "record_video_size": viewport}

        if self.launch_mode == "existing":
            if not self.cdp_endpoint:
                raise RuntimeError("launch_mode=existing 需要 cdp_endpoint(如 http://127.0.0.1:9222)")
            browser = p.chromium.connect_over_cdp(self.cdp_endpoint)
            context = browser.contexts[0] if browser.contexts else browser.new_context()
            page = context.pages[0] if context.pages else context.new_page()
            if self.video_dir:
                print("  (existing 模式连的是已开浏览器,全程视频不可用;截图仍正常)")
            return context, browser, page, False

        if self.launch_mode == "persistent":
            udd = self.user_data_dir or ".auth/_persistent"
            Path(udd).mkdir(parents=True, exist_ok=True)
            kwargs: dict[str, Any] = {"headless": headless_eff, "viewport": viewport, **rec}
            try:
                context = p.chromium.launch_persistent_context(udd, channel=self.channel, **kwargs)
            except Exception as e:  # noqa: BLE001  真 Chrome 不在就退回 Chromium
                print(f"  (真 Chrome 不可用,退回 Chromium: {e})")
                context = p.chromium.launch_persistent_context(udd, **kwargs)
            page = context.pages[0] if context.pages else context.new_page()
            self._seed_cookies(context)   # 首跑引种:把 .auth 里的 cookie 灌进新 profile
            return context, None, page, True

        # isolated(默认/现状)
        browser = p.chromium.launch(headless=headless_eff)
        ctx_kwargs: dict[str, Any] = {"viewport": viewport, **rec}
        if self.session_file and Path(self.session_file).exists():
            ctx_kwargs["storage_state"] = self.session_file
        context = browser.new_context(**ctx_kwargs)
        page = context.new_page()
        return context, browser, page, True

    def _seed_cookies(self, context) -> None:
        """persistent profile 首跑无登录态时,用已保存的 storageState 里的 cookie 引种一次。"""
        if not (self.session_file and Path(self.session_file).exists()):
            return
        try:
            if context.cookies():      # profile 已带登录态,无需引种
                return
            state = json.loads(Path(self.session_file).read_text(encoding="utf-8"))
            cookies = state.get("cookies") or []
            if cookies:
                context.add_cookies(cookies)
                print(f"  (persistent 首跑:注入 {len(cookies)} 条 cookie 引种登录态)")
        except Exception as e:  # noqa: BLE001
            print(f"  (cookie 引种跳过: {e})")

    def _on_response(self, response) -> None:  # playwright Response
        try:
            req = response.request
            if req.resource_type not in ("xhr", "fetch"):
                return
            if self.url_pattern and self.url_pattern not in response.url:
                return

            body = None
            try:
                post = req.post_data
                body = json.loads(post) if post else None
            except Exception:  # noqa: BLE001
                body = req.post_data

            resp_json = None
            try:
                resp_json = response.json()
            except Exception:  # noqa: BLE001
                resp_json = None  # 非 JSON 返回,跳过

            self.captures.append(Capture(
                url=response.url,
                method=req.method,
                resource_type=req.resource_type,
                request_body=body,
                query_params=self._parse_query(response.url),
                status=response.status,
                response_json=resp_json,
            ))
        except Exception:  # noqa: BLE001  探针不能因单个响应异常而中断
            pass

    @staticmethod
    def _parse_query(url: str) -> dict[str, str]:
        from urllib.parse import urlparse, parse_qsl
        return dict(parse_qsl(urlparse(url).query))

    # ───────────────────────── 落盘 / 挑选 ─────────────────────────

    def save(self, out_dir: str | Path, feature: str) -> Path:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{feature}_{int(time.time())}.json"
        path.write_text(
            json.dumps([asdict(c) for c in self.captures], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return path

    def pick_search_call(self) -> Capture | None:
        """
        从捕获里挑出最像'检索'的那一次:响应体含列表 + 有分页/总数迹象,优先 POST。
        给自动建模用;挑错了人可在审阅时改。
        """
        def score(c: Capture) -> int:
            s = 0
            rj = c.response_json or {}
            data = rj.get("data") if isinstance(rj, dict) else None
            if isinstance(data, dict):
                if any(k in data for k in ("list", "rows", "records")):
                    s += 5
                if any(k in data for k in ("total", "totalCount", "count")):
                    s += 3
            if c.method == "POST":
                s += 1
            if any(k in c.url.lower() for k in ("search", "query", "list", "page")):
                s += 2
            return s

        scored = [(score(c), c) for c in self.captures]
        scored = [(s, c) for s, c in scored if s > 0]
        if not scored:
            return None
        # 同分取最新一次:驱动/录制里最后那次检索(带筛选)才是人想测的,
        # 而非页面加载时的空筛选请求。
        scored.sort(key=lambda x: (x[0], x[1].ts), reverse=True)
        return scored[0][1]

    def _install_capture_only(self, context, read_ok: tuple | None = None) -> None:
        """安全录模式:拦写/动作 POST(非只读、命中 url_pattern),记 body 后 abort(不落服务端)。"""
        import json as _json
        oks = tuple(read_ok) if read_ok else self._READ_OK_DEFAULT
        patt = self.url_pattern or "/api/"

        def handler(route):
            req = route.request
            path = req.url.split("?")[0]
            hit = (patt in path) and req.method in ("POST", "PUT", "PATCH") \
                and not any(k in path for k in oks)
            if hit:
                try:
                    body = _json.loads(req.post_data) if req.post_data else None
                except Exception:  # noqa: BLE001
                    body = req.post_data
                self.captures.append(Capture(url=req.url, method=req.method,
                                             resource_type="xhr", request_body=body,
                                             response_json=None))
                try:
                    route.abort()
                except Exception:  # noqa: BLE001
                    route.continue_()
                return
            route.continue_()

        try:
            context.route("**/*", handler)
        except Exception:  # noqa: BLE001
            pass

    def pick_write_call(self) -> Capture | None:
        """从捕获里挑最像'写'的那次:POST/PUT/PATCH + 带 JSON 请求体 + url 含写动作词 + 响应示成功。
        写入类自动建模用:probe 录一次写操作即得 endpoint + 提交体模板,免人工指定接口。"""
        WRITE_HINTS = ("save", "submit", "create", "draft", "add", "update", "edit",
                       "insert", "new", "confirm", "apply")

        def score(c: Capture) -> int:
            if c.method not in ("POST", "PUT", "PATCH"):
                return 0
            s = 3
            if isinstance(c.request_body, dict) and c.request_body:
                s += 3
            if any(h in c.url.lower() for h in WRITE_HINTS):
                s += 3
            rj = c.response_json or {}
            if isinstance(rj, dict) and (rj.get("success") is True or rj.get("code") in (0, 200)):
                s += 2
            # 排除明显的检索(响应是列表/分页),避免把"查"当成"写"
            data = rj.get("data") if isinstance(rj, dict) else None
            if isinstance(data, dict) and any(k in data for k in ("list", "rows", "records")):
                s -= 4
            return s

        scored = [(score(c), c) for c in self.captures if score(c) > 0]
        if not scored:
            return None
        scored.sort(key=lambda x: (x[0], x[1].ts), reverse=True)
        return scored[0][1]


def write_stub_from_capture(capture: Capture) -> dict:
    """把一次写调用的抓包转成写路由桩:endpoint(method+path) + template_body(提交体模板)。
    probe 产出这个桩后,route 的 endpoint/template 就不用人手写了(skill 存模板文件再引用即可)。"""
    from urllib.parse import urlparse
    path = urlparse(capture.url).path or capture.url
    return {"endpoint": {"method": capture.method, "url": path},
            "template_body": capture.request_body}
