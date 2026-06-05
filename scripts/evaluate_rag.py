import argparse
import json
from pathlib import Path
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.services.rag_service import query_rag, init_vector_db

# 預先定義 100 個針對東吳大學法規的真實高質量問題
FAQ_QUESTIONS = [
    # 1. 東吳大學學生工讀助學實施辦法 (10題)
    "學生工讀助學金的每小時給付標準是多少？",
    "工讀助學金的經費來源主要有哪些？",
    "學生申請工讀需要具備哪些基本資格？",
    "哪些學生在申請工讀時可以獲得優先考量？",
    "工讀生的考核是由誰負責？考核不合格會怎樣？",
    "工讀生如果因故請假，應該如何辦理？",
    "學生工讀期間的保險有什麼規定？",
    "工讀生可以同時在多個單位工讀嗎？",
    "每位工讀生每個月的工讀時數上限是多少？",
    "工讀助學實施辦法的目的與宗旨是什麼？",

    # 2. 東吳大學研究生獎助學金辦法 (10題)
    "研究生獎助學金的分配原則是什麼？",
    "碩士生與博士生的獎助學金給付標準有何不同？",
    "研究生領取獎助學金需要盡哪些義務或協助哪些工作？",
    "研究生如何申請獎助學金？需要提交哪些文件？",
    "領取研究生獎助學金期間，如果辦理休學會如何處理？",
    "研究生獎助學金的經費來源有哪些？",
    "如果研究生在校外有全職工作，還可以領取此獎助學金嗎？",
    "研究生助理的工作時數有何規定？",
    "研究生獎助學金的發放時間與頻率為何？",
    "此辦法中所指的卓越或優秀研究生有哪些獎勵方式？",

    # 3. Soochow University Student Leave Regulations (10題)
    "心理調適假最多可以請幾天？",
    "申請心理調適假單次最多可以請幾天？",
    "請事假需要提出證明文件嗎？",
    "病假如果超過幾天需要出具醫療診斷證明？",
    "生理假的請假規定是什麼？一學期可以請幾天？",
    "請假如果沒有及時辦理，銷假或補請的期限是多久？",
    "考試期間如果因病請假，應該如何補救？",
    "喪假的給假天數與範圍是如何規定的？",
    "公假的申請條件有哪些？需要哪些證明？",
    "如果請假天數過多，會不會影響該學期的學業成績或操行？",

    # 4. 東吳大學校外學生宿舍輔導及管理辦法 (10題)
    "宿舍輔導或管理人員在未獲得學生同意下，可以隨意進入寢室檢查嗎？",
    "宿舍安全檢查通常在什麼情況下可以進行？需要誰的同意？",
    "學生申請校外宿舍需要符合哪些條件？",
    "校外宿舍的收費與退費規則是什麼？",
    "住宿學生在宿舍內有哪些必須遵守的公共規範？",
    "如果住宿學生違反宿舍規定，會有什麼懲處？",
    "校外宿舍的門禁時間是如何規定的？",
    "訪客進入校外宿舍有哪些規定與限制？",
    "宿舍的設備損壞時，應該向誰申報修繕？",
    "校外學生宿舍的輔導與關懷工作由誰負責？",

    # 5. 東吳大學優秀應屆畢業生選拔及獎勵辦法 (6題)
    "優秀應屆畢業生的選拔標準是什麼？",
    "獲選為優秀應屆畢業生可以獲得什麼獎勵？",
    "優秀應屆畢業生選拔的推薦與審查程序為何？",
    "選拔推薦需要填寫或準備哪些佐證資料？",
    "哪些因素會導致已獲選的優秀畢業生資格被取消？",
    "每學年度各學系推薦優秀畢業生的名額限制是多少？",

    # 6. 東吳大學碩、博士班優秀新生獎勵辦法 (6題)
    "碩、博士班優秀新生的獎勵對象包括哪些學生？",
    "獲選的優秀新生可以免除學雜費或獲得多少獎學金？",
    "優秀新生獎勵的續撥條件是什麼？（例如學業成績要求）",
    "優秀新生獎勵的審查委員會由哪些成員組成？",
    "如果新生入學後辦理休學，其獎勵資格會保留嗎？",
    "優秀新生獎勵的經費來源為何？",

    # 7. 東吳大學學生銷過實施辦法 (6題)
    "學生申請銷過的資格或前置條件是什麼？",
    "記小過或大過的學生，分別需要在考核期內表現良好多久才能申請銷過？",
    "銷過申請的流程與審批步驟為何？",
    "銷過核准後，學生的懲處紀錄在成績單上會如何顯示？",
    "銷過考核期內如果再次違規，會有什麼後果？",
    "一學期內最多可以申請幾次銷過？",

    # 8. 東吳大學清寒急難救助金實施辦法 (6題)
    "學生遇到什麼樣的急難情況可以申請此救助金？",
    "清寒急難救助金的申請期限是多久？（事件發生後多久內）",
    "申請清寒急難救助金需要檢附哪些清寒或急難證明文件？",
    "救助金的核發金額上限與級距是多少？",
    "急難救助金的經費撥付流程與審核時間多長？",
    "急難救助金的審查小組由哪些單位的人員組成？",

    # 9. 東吳大學端木愷校長獎學金實施要點 (6題)
    "端木愷校長獎學金的申請對象與資格要求為何？",
    "此獎學金每學期的名額與獎勵金額是多少？",
    "申請端木愷校長獎學金需要準備哪些資料？",
    "獎學金的評選指標有哪些？（例如學術成績、操行）",
    "端木愷校長獎學金的獲獎學生有何義務或需要參與哪些活動？",
    "此獎學金的經費來源與設立宗旨是什麼？",

    # 10. 東吳大學學生社團組織及活動辦法 (6題)
    "學生社團如何申請成立？需要多少發起人？",
    "社團舉辦校外活動需要提前多久向學校報備或申請？",
    "學生社團評鑑的指標與考核方式為何？",
    "社團經費的補助申請與核銷流程是什麼？",
    "若社團管理不當或違反校規，會面臨什麼樣的懲處或停權？",
    "社團指導老師的聘任與權責有哪些規定？",

    # 11. 東吳大學獎助學金申請審核辦法 (6題)
    "學生申請各類獎助學金的一般性資格限制有哪些？",
    "獎助學金的審核委員會如何進行審查與決議？",
    "重複申領多項獎助學金有什麼樣的限制與規定？",
    "獎助學金申請逾期的處理規定是什麼？",
    "如果申請資料造假，學生會受到什麼樣的處分？",
    "獎助學金發放的帳戶設定與撥款時序為何？",

    # 12. 東吳大學優良導師獎勵辦法 (6題)
    "優良導師的遴選標準與資格有哪些？",
    "獲選為優良導師可以獲得什麼樣的獎勵或表揚？",
    "優良導師的推薦管道與遴選委員會組成？",
    "遴選評分中，學生的意見或評量佔多少比例？",
    "優良導師選拔的頻率為何？每幾年舉辦一次？",
    "優良導師的獎勵經費來源是什麼？",

    # 13. 東吳大學學生會會費代收辦法 (6題)
    "學生會會費的代收金額與收費標準如何訂定？",
    "學生是否可以選擇不繳交或申請退費？退費手續為何？",
    "學校代收的學生會會費如何轉撥給學生會？",
    "代收會費的流向與經費監督機制是什麼？",
    "如果代收會費的使用出現爭議，如何協調解決？",
    "學生會會費代收辦法的修正程序為何？",

    # 14. 東吳大學獎助學金暨優秀學生甄選委員會組織章程 (5題)
    "此委員會的主要職掌與功能有哪些？",
    "委員會的召集人由誰擔任？成員包括哪些行政單位代表？",
    "委員會議召開的法定人數與決議門檻是多少？",
    "委員會委員的任期是多久？如何更替？",
    "委員會決議的案子如何向校長及相關會議提報？",

    # 15. 東吳大學學生獎懲委員會組織章程 (5題)
    "學生獎懲委員會的主要職權與審議範圍為何？",
    "獎懲委員會的委員組成中，有沒有包含學生代表？",
    "當學生不服懲處決定時，可以在會中如何申訴或申辯？",
    "委員會議決議的通過門檻與匿名投票規則為何？",
    "委員會召開會議的頻率以及臨時會議的召開條件？"
]

def write_outputs(results: list[dict], output_dir: Path, total_time: float) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "rag-evaluation.json"
    markdown_path = output_dir / "rag-evaluation.md"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    average = total_time / len(results) if results else 0
    lines = [
        "# RAG evaluation",
        "",
        f"- Questions: {len(results)}",
        f"- Total time: {total_time:.2f} seconds",
        f"- Average time: {average:.2f} seconds",
        "",
    ]
    for item in results:
        lines.extend(
            [
                f"## {item['id']}. {item['question']}",
                "",
                item["answer"],
                "",
                f"Sources: {', '.join(item['sources']) or 'none'}",
                f"Time: {item['time_seconds']} seconds",
                "",
            ]
        )
    markdown_path.write_text("\n".join(lines), encoding="utf-8")


def run_evaluation(output_dir: Path, limit: int | None, model: str, ollama_base_url: str) -> None:
    questions = FAQ_QUESTIONS[:limit] if limit else FAQ_QUESTIONS
    print(f"Running {len(questions)} local RAG evaluation questions with {model}.")

    import os

    os.environ["OLLAMA_CHAT_MODEL"] = model
    os.environ["OLLAMA_BASE_URL"] = ollama_base_url
    db = init_vector_db()
    if not db:
        raise RuntimeError("Vector database is not ready.")

    results = []
    start_time = time.time()

    for idx, question in enumerate(questions, 1):
        print(f"[{idx:03d}/{len(questions)}] {question}")
        q_start = time.time()
        try:
            response = query_rag(question, api_key=None, db=db, disable_expansion=True)
            elapsed = time.time() - q_start
            results.append({
                "id": idx,
                "question": question,
                "answer": response["answer"],
                "sources": response["sources"],
                "engine_type": response["engine_type"],
                "time_seconds": round(elapsed, 2),
            })
        except Exception as exc:
            results.append({
                "id": idx,
                "question": question,
                "answer": f"Evaluation failed: {exc}",
                "sources": [],
                "engine_type": "error",
                "time_seconds": 0.0,
            })
        if idx % 5 == 0:
            write_outputs(results, output_dir, time.time() - start_time)

    write_outputs(results, output_dir, time.time() - start_time)
    print(f"Results written to {output_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the local SCU law RAG benchmark.")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts") / "evaluation")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--model", default="gemma3")
    parser.add_argument("--ollama-base-url", default="http://localhost:11434")
    args = parser.parse_args()
    run_evaluation(args.output_dir, args.limit, args.model, args.ollama_base_url)
