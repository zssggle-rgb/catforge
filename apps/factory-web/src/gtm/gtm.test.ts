import { afterEach, describe, expect, it, vi } from "vitest";
import { defaultFilters, displayValue, readRoute, type Scope, type View } from "./contract";
import { gtm } from "./client";

const scope: Scope = {...defaultFilters("TV"), project_id: "A/B", page: "competitor", tab: "product", offset: 0, limit: 20};
const view: View = {version: "1", project_id: "A/B", category_code: "TV", page: "competitor", tab: "product", snapshot_id: "v1",
  as_of: null, status: "partial", notice: "暂无可比市场数据", insights: [], charts: [], metrics: [], tables: [], actions: []};
const signal = new AbortController().signal;
function serve(data: unknown, status = 200) {
  const fetcher = vi.fn().mockImplementation(async () => new Response(JSON.stringify(data), {status, headers: {"Content-Type": "application/json"}}));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
afterEach(() => vi.unstubAllGlobals());
describe("GTM Web", () => {
  it("keeps missing values distinct from zero", () => {
    for (const v of [null, undefined, "", "-"]) expect(displayValue(v, "台")).toBe("—");
    expect(displayValue(0, "台")).toBe("0台");
  });
  it("supports the landing page, browser history and encoded conversation identifiers", () => {
    expect(readRoute("#/reports").route).toBe("reports");
    expect(readRoute("#/chat/a%2Fb")).toEqual({route: "chat", conversation: "a/b"});
    expect(readRoute("#/chat/%").conversation).toBe("");
    for (const path of ["", "#/unknown", "#/constructor"]) expect(readRoute(path).route).toBe("daily");
  });
  it("sends project scope, repeated competitor IDs and cancellation to the configured gateway", async () => {
    const fetcher = serve(view);
    expect(await gtm.view({...scope, competitor_ids: ["TCL", "创维"]}, signal)).toEqual(view);
    const [path, init] = fetcher.mock.calls[0];
    const url = new URL(path, "http://localhost");
    expect(url.pathname).toBe("/api/gtm/v1/projects/A%2FB/views/competitor");
    expect(url.searchParams.getAll("competitor_ids")).toEqual(["TCL", "创维"]);
    expect(url.searchParams.get("category_code")).toBe("TV");
    expect(url.searchParams.has("date_from")).toBe(false);
    expect(init.signal).toBe(signal);
  });
  it.each([{project_id: "B"}, {category_code: "AC"}, {tab: "other"}, {tables: null}])("rejects a mismatched snapshot %o", async patch => {
    serve({...view, ...patch});
    await expect(gtm.view(scope, signal)).rejects.toThrow("不一致");
  });
  it("surfaces upstream failure and an unconfigured SPA fallback", async () => {
    serve({message: "当前用户无权查看"}, 403);
    await expect(gtm.context(signal)).rejects.toThrow("无权");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html/>")));
    await expect(gtm.context(signal)).rejects.toThrow("尚未就绪");
  });
  it("validates the environment before displaying any sample or live workspace", async () => {
    serve({version: "1", mode: "test"});
    await expect(gtm.context(signal)).rejects.toThrow("格式");
  });
  it("submits the receipt key, source snapshot and object without optimistic completion", async () => {
    const fetcher = serve({message: "快照已变化"}, 409);
    await expect(gtm.act(scope, "complete-task", "task-1", "", "retry-1", "snapshot-9", {})).rejects.toThrow("快照已变化");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({request_id: "retry-1", snapshot_id: "snapshot-9", row_id: "task-1", scope});
  });
  it("keeps conversation, catalog and history reads in the selected category", async () => {
    const fetcher = serve([]);
    await gtm.choices("p","TV","competitor","查询",signal); await gtm.history("p","TV",signal); await gtm.conversation("p","TV","a/b",signal);
    expect(fetcher.mock.calls.every(([url]) => new URL(url,"http://localhost").searchParams.get("category_code") === "TV")).toBe(true);
    expect(fetcher.mock.calls[2][0]).toContain("a%2Fb");
  });
  it("binds a follow-up to the selected snapshot and uploaded attachments", async () => {
    const fetcher = serve({id: "c1", label: "分析", messages: []});
    const origin = {page: scope.page, tab: scope.tab, snapshot_id: "s1"};
    await gtm.ask("p",scope,null,"问题","u1",origin,["file1"]);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toMatchObject({origin, attachment_ids:["file1"], question:"问题", request_id:"u1"});
  });
  it("uploads a file as binary under the selected project and purpose", async () => {
    const fetcher = serve({id:"f1", name:"样例.csv"},201); const file = new File(["a,b"], "样例.csv");
    await gtm.attach("p","TV",file,"floor");
    expect(fetcher.mock.calls[0][1].body).toBe(file);
    expect(new URL(fetcher.mock.calls[0][0], "http://localhost").searchParams.get("filename")).toBe("样例.csv");
  });
});
