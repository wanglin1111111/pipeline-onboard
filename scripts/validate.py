#!/usr/bin/env python3
"""validate.py — pipeline-onboard Pipeline 工具接入计划七维校验器

输入: Pipeline 工具接入计划 JSON（schema 见 tests/sample_good.json）
  {
    "gate": {
      "platforms_active": 4,               // 每周实际登录发布的平台数（≥3）
      "weekly_outputs_4w_avg": 4,          // 过去 4 周平均每周产出条数（≥3）
      "payback_weeks": 3,                  // 回本周期（≤8）
      "boundary_check": {                  // 开源边界检查（部署前必填）
        "self_hosted_core": ["发布", "排期", "分发"],
        "official_required": ["任务市场", "收益结算"],
        "data_ownership_checked": true     // 数据归属已查（素材/授权/粉丝/收益分别在哪）
      }
    },
    "phase1_distribution": {               // 阶段 1：单环节切入（分发）
      "only_one_stage": true,              // 验证期只切一个环节
      "before_min_per_item": 20,           // 切换前单条分发耗时（分）
      "after_min_per_item": 8,             // 切换后（≤ before 的 50%）
      "incidents": 0,                      // 分发事故数（发错平台/时间/漏发/封面错位）
      "verified_weeks": 2                  // 连续验证周数（≥2）
    },
    "phase2_calendar": {                   // 阶段 2：节奏改造
      "calendar_coverage_days": 7,         // 日历覆盖天数无空档（≥7）
      "ad_hoc_decisions_per_week": 0,      // 每周临时决策次数（=0）
      "quality_variance_down": true        // 批产条互动数据方差 ≤ 改造前
    },
    "phase3_fallback": {                   // 阶段 3：人工兜底分级
      "grading_configured": true,          // 分级规则写成配置（非人肉判断）
      "high_intent_human_review": 1.0,     // 高意向评论人审率（=1.0 硬线）
      "negative_ai_sent": 0,               // 负面评论 AI 发出数（=0 硬线）
      "weekly_audit_done": true            // 每周抽查分类正确率（高意向≥95%/负面≥98%）
    },
    "phase4_mcp": {                        // 阶段 4：MCP 接入
      "integrated": true,
      "min_chain_passed": 3,               // 最小调用链 3/3（发布触发/状态查询/兜底协同）
      "window_switches_per_week": 0,       // 为用工具切窗口次数（=0）
      "functions_fixed": 3                 // 固化的常用函数数（≥3）
    },
    "phase5_monetization": {               // 阶段 5：变现（最后碰）
      "started": false,                    // 未开始=false（合规）；已开始须满足前置
      "prerequisites_weeks": [2, 2, 2],    // 分发/节奏/兜底各稳定周数（各 ≥2）
      "min_task_completed": false,         // 最小任务走完结算全链（接单→交付→结算→到账）
      "settlement_matches_advertised": null, // 口径与宣传是否一致（未验证=null；不一致=false 禁止加大）
      "official_rules_checked": true       // 以平台官方规则和结算记录为准（已逐条核）
    }
  }

七维校验（任一 FAIL → exit 1）：
  D1 判断闸门: platforms_active ≥3 且 weekly_outputs_4w_avg ≥3 且 payback_weeks ≤8；
     开源边界检查已做（self_hosted_core/official_required 均已列、data_ownership_checked=true）
     ——不满足画像的人部署 = 部署成本 > 收益，数学必然
  D2 单环节切入: only_one_stage=true 且 after ≤ 0.5×before 且 before>0
     且 incidents=0 且 verified_weeks ≥2（数字验收+零事故，"感觉快了"不算）
  D3 节奏改造: calendar_coverage_days ≥7 且 ad_hoc_decisions_per_week=0
     且 quality_variance_down=true（只做分发不做日历 = 杠杆没用上）
  D4 兜底分级: grading_configured=true 且 high_intent_human_review=1.0（硬线）
     且 negative_ai_sent=0（硬线，破一次即回炉）且 weekly_audit_done=true
  D5 MCP 接入: integrated=true 且 min_chain_passed=3（3/3 最小调用链）
     且 window_switches_per_week=0 且 functions_fixed ≥3
     （"另一个工具"变"工作流里的函数"= 长期用下去的分水岭）
  D6 变现纪律: started=false → 合规（最后碰，未碰是正确状态）；
     started=true 时：prerequisites_weeks 各 ≥2 且 min_task_completed=true 且
     settlement_matches_advertised 不得为 false（口径不一致禁止加大投入）
     且 official_rules_checked=true（以官方规则和结算记录为准）
  D7 顺序纪律: 阶段依赖检查——phase2 生效须 phase1 验收过；phase3 须 phase2；
     phase4 须 phase1（MCP 接在验证跑通的环节上）；phase5 started=true 须
     phase2+phase3 各自验收过。跳级（前置未验收而后置生效）= 拦截

退出码：0=通过 / 1=有缺陷 / 2=文件/格式错误
"""
import json
import sys


def fail(checks, code, msg):
    checks.append(("FAIL", code, msg))


def ok(checks, code, msg):
    checks.append(("OK", code, msg))


def is_nonempty_list(v):
    return isinstance(v, list) and any(x for x in v)


def validate(plan):
    checks = []

    g = plan.get("gate") or {}
    p1 = plan.get("phase1_distribution") or {}
    p2 = plan.get("phase2_calendar") or {}
    p3 = plan.get("phase3_fallback") or {}
    p4 = plan.get("phase4_mcp") or {}
    p5 = plan.get("phase5_monetization") or {}

    # D1 判断闸门
    pa, wo, pb = g.get("platforms_active"), g.get("weekly_outputs_4w_avg"), g.get("payback_weeks")
    bc = g.get("boundary_check") or {}
    if not isinstance(pa, int) or pa < 3:
        fail(checks, "D1", f"platforms_active={pa!r}——每周实际发布平台 <3，部署成本>收益，别碰")
    elif not isinstance(wo, (int, float)) or wo < 3:
        fail(checks, "D1", f"weekly_outputs_4w_avg={wo!r}——过去 4 周平均每周产出 <3 条，频率不够摊不平部署成本")
    elif not isinstance(pb, (int, float)) or pb <= 0 or pb > 8:
        fail(checks, "D1", f"payback_weeks={pb!r}——回本周期 >8 周 = 别上（单平台低频的数学必然）")
    else:
        if not is_nonempty_list(bc.get("self_hosted_core")) or not is_nonempty_list(bc.get("official_required")):
            fail(checks, "D1", "开源边界检查未做——自托管能干什么/什么走官方服务器 必须部署前列清（'开源'≠'全可控'）")
        elif bc.get("data_ownership_checked") is not True:
            fail(checks, "D1", "data_ownership_checked=false——数据归属没查（素材/授权/粉丝/收益存在哪、能带走吗）")
        else:
            ok(checks, "D1", f"闸门通过（{pa} 平台 + 周产 {wo} 条 + {pb} 周回本 + 边界已查）")

    # D2 单环节切入
    b = p1.get("before_min_per_item")
    a = p1.get("after_min_per_item")
    if p1.get("only_one_stage") is not True:
        fail(checks, "D2", "only_one_stage=false——验证期同时切多个环节 = 出问题无法归因")
    elif not isinstance(b, (int, float)) or b <= 0:
        fail(checks, "D2", f"before_min_per_item={b!r}——先实测切换前基线（不凭记忆）")
    elif not isinstance(a, (int, float)) or a < 0 or a > 0.5 * b:
        fail(checks, "D2", f"切换后 {a!r} > 切换前 {b} 的 50%——省时间没达标（工具退化成'加了个后台'）")
    elif p1.get("incidents") != 0:
        fail(checks, "D2", f"incidents={p1.get('incidents')}——分发有事故（发错平台/时间/漏发），零事故是验收硬指标")
    elif not isinstance(p1.get("verified_weeks"), int) or p1.get("verified_weeks") < 2:
        fail(checks, "D2", f"verified_weeks={p1.get('verified_weeks')!r}——须连续 ≥2 周数字验收（一周=运气）")
    else:
        ok(checks, "D2", f"分发切入验收过（{b}→{a} 分/条，{p1['verified_weeks']} 周零事故）")

    # D3 节奏改造
    cov = p2.get("calendar_coverage_days")
    adh = p2.get("ad_hoc_decisions_per_week")
    if not isinstance(cov, int) or cov < 7:
        fail(checks, "D3", f"calendar_coverage_days={cov!r}——日历覆盖率 <7 天无空档，批生产节奏没建成")
    elif adh != 0:
        fail(checks, "D3", f"ad_hoc_decisions_per_week={adh!r}——还有'今天发什么'临时决策，杠杆没用上")
    elif p2.get("quality_variance_down") is not True:
        fail(checks, "D3", "quality_variance_down=false——批产后质量方差没降（批量≠铺量，质量波动=改造失败）")
    else:
        ok(checks, "D3", f"日历驱动建成（{cov} 天无空档，临时决策 0 次，质量方差下降）")

    # D4 兜底分级
    hir = p3.get("high_intent_human_review")
    nas = p3.get("negative_ai_sent")
    if p3.get("grading_configured") is not True:
        fail(checks, "D4", "grading_configured=false——分级规则没写成配置，每次人肉判断=机制不存在")
    elif not isinstance(hir, (int, float)) or abs(hir - 1.0) > 1e-9:
        fail(checks, "D4", f"high_intent_human_review={hir!r}——高意向评论人审率必须 100%（AI 对外发言最后一秒留给人）")
    elif nas != 0:
        fail(checks, "D4", f"negative_ai_sent={nas}——负面评论被 AI 发出=公关事故，立即停自动回复回炉查分类器")
    elif p3.get("weekly_audit_done") is not True:
        fail(checks, "D4", "weekly_audit_done=false——分类器会漂移（新梗/新变体），每周抽查不做了=漏检在累积")
    else:
        ok(checks, "D4", "兜底分级合规（高意向 100% 人审 + 负面 AI 零发出 + 每周抽查）")

    # D5 MCP 接入
    if p4.get("integrated") is not True:
        fail(checks, "D5", "integrated=false——工具还是'另一个后台'=部署两周吃灰的经典路径，MCP 是长期用的分水岭")
    elif p4.get("min_chain_passed") != 3:
        fail(checks, "D5", f"min_chain_passed={p4.get('min_chain_passed')!r}——最小调用链须 3/3（发布触发/状态查询/兜底协同）")
    elif p4.get("window_switches_per_week") != 0:
        fail(checks, "D5", f"window_switches_per_week={p4.get('window_switches_per_week')!r}——还在为用工具切窗口=入口摩擦没消除")
    elif not isinstance(p4.get("functions_fixed"), int) or p4.get("functions_fixed") < 3:
        fail(checks, "D5", f"functions_fixed={p4.get('functions_fixed')!r}——常用函数须固化 ≥3 个（没固化=快捷指令不是函数）")
    else:
        ok(checks, "D5", f"MCP 接入完成（调用链 3/3 + 切窗口 0 + {p4['functions_fixed']} 个函数固化）")

    # D6 变现纪律
    if p5.get("started") is not True:
        if p5.get("official_rules_checked") is not True:
            fail(checks, "D6", "official_rules_checked=false——变现未开始也要先核官方规则（口径/数据归属/结算周期）")
        else:
            ok(checks, "D6", "变现未开始（正确状态：最后碰，前置未齐不碰）+ 官方规则已预核")
    else:
        pre = p5.get("prerequisites_weeks") or []
        if len(pre) < 3 or any(not isinstance(x, int) or x < 2 for x in pre):
            fail(checks, "D6", f"prerequisites_weeks={pre!r}——变现三前置（分发/节奏/兜底）须各 ≥2 周稳定")
        elif p5.get("min_task_completed") is not True:
            fail(checks, "D6", "min_task_completed=false——最小任务没走完结算全链（接单→交付→结算→到账）前不得加大投入")
        elif p5.get("settlement_matches_advertised") is False:
            fail(checks, "D6", "settlement_matches_advertised=false——结算口径与宣传不一致=停，查官方规则原文，禁止加大投入")
        elif p5.get("official_rules_checked") is not True:
            fail(checks, "D6", "official_rules_checked=false——涉及真实收益，一切以平台官方规则和结算记录为准")
        else:
            ok(checks, "D6", f"变现纪律合规（前置 {pre} 周 + 最小任务已走全链 + 官方规则已核）")

    # D7 顺序纪律（阶段依赖）
    order_issues = []

    def passed1():
        return (p1.get("only_one_stage") is True and isinstance(b, (int, float)) and b > 0
                and isinstance(a, (int, float)) and a <= 0.5 * b
                and p1.get("incidents") == 0
                and isinstance(p1.get("verified_weeks"), int) and p1.get("verified_weeks") >= 2)

    def passed2():
        return (isinstance(cov, int) and cov >= 7 and adh == 0 and p2.get("quality_variance_down") is True)

    def passed3():
        return (p3.get("grading_configured") is True and isinstance(hir, (int, float))
                and abs(hir - 1.0) <= 1e-9 and nas == 0 and p3.get("weekly_audit_done") is True)

    p2_active = isinstance(cov, int) and cov >= 7
    p3_active = p3.get("grading_configured") is True
    p4_active = p4.get("integrated") is True
    p5_active = p5.get("started") is True

    if p2_active and not passed1():
        order_issues.append("节奏改造生效但分发环节未验收")
    if p3_active and not (passed1() and passed2()):
        order_issues.append("互动兜底生效但分发/排期未验收")
    if p4_active and not passed1():
        order_issues.append("MCP 已接入但分发环节未验收（接在没验证的环节上）")
    if p5_active and not (passed1() and passed2() and passed3()):
        order_issues.append("变现已启动但分发/排期/兜底未全部验收（跳级）")
    if order_issues:
        fail(checks, "D7", "顺序纪律: " + "；".join(order_issues) + "——分发→排期→互动→变现不可跳级")
    else:
        ok(checks, "D7", "阶段依赖合规（无跳级）")

    return checks


def main():
    if len(sys.argv) != 2:
        print("usage: python validate.py plan.json", file=sys.stderr)
        return 2
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            plan = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: 无法读取/解析: {e}", file=sys.stderr)
        return 2
    if not isinstance(plan, dict):
        print("ERROR: 顶层必须是 JSON 对象", file=sys.stderr)
        return 2

    checks = validate(plan)
    fails = [c for c in checks if c[0] == "FAIL"]
    for status, code, msg in checks:
        if status == "FAIL":
            print(f"[{code}] FAIL {msg}")
    print(f"== {len(checks) - len(fails)} OK / {len(fails)} FAIL ==")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
