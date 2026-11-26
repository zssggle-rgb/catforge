import { describe, expect, it } from "vitest";
import { projectDetail, type DetailProjection } from "./projection";
import { detailScreens, type DetailKind } from "./screens";

function make(kind: DetailKind): DetailProjection {
  return {version:"0916",project_id:"p",category_code:"TV",snapshot_id:"s",record_id:"r",kind,title:"记录",
    values:{},lists:{},tables:{},evidence:[],links:[]};
}
describe("0916 detailed views",()=>{
  it.each(Object.keys(detailScreens) as DetailKind[])("renders %s without sample records or executable handlers",kind=>{
    const body=document.createElement("div");
    body.append(projectDetail(make(kind),document));
    expect(body.querySelectorAll("*").length).toBeGreaterThan(0);
    expect(body.innerHTML).not.toMatch(/ onclick=| oninput=|65E55N|2,899|张恩哲|小蓝翼|2026-09|65Q9L|98.6%/);
  });
  it("uses only current fields, preserves zero, and treats user data as text",()=>{
    const data=make("own-evidence");data.values={model:"<b>型号</b>", paid_price:0, floor_price:null};
    const body=document.createElement("div");body.append(projectDetail(data,document));
    expect(body.querySelector("#evidenceProduct")?.innerHTML).toBe("&lt;b&gt;型号&lt;/b&gt;");
    expect(body.querySelector("#evidenceCurrent")?.textContent).toBe("0");
    expect(body.querySelector("#evidenceBaseline")?.textContent).toBe("—");
  });
  it("repeats history records and product claims from a returned snapshot",()=>{
    const data=make("rival-price-history");data.tables.history={columns:["时间","到手价"],rows:[["周一",3200],["周二",null]]};
    const body=document.createElement("div");body.append(projectDetail(data,document));
    expect([...body.querySelectorAll("tbody td")].map(el=>el.textContent)).toEqual(["周一","3,200","周二","—"]);
    const p=make("launch-encyclopedia");p.lists.claims=["低反射","144 Hz"];body.replaceChildren(projectDetail(p,document));
    expect(body.querySelector("#launchModalPoints")?.children).toHaveLength(2);
  });
});
