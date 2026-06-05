# 2026 Local RAG Benchmark

這是 2026 年開發期間的一次歷史快照，不是通用效能或正確率保證。

## 方法

- 資料：倉庫內 15 份東吳大學法規與當時的 `faq_cache.json`
- 題目：104 題，涵蓋工讀、獎助學金、請假、宿舍、社團與獎懲
- 檢索：Chroma dense retrieval、BM25 與 RRF fusion
- 推論：本機 Ollama / Gemma 3
- 模式：關閉 query expansion，逐題產生回答並記錄來源與時間

## 歷史結果

| 指標 | 結果 |
| --- | --- |
| 題數 | 104 |
| 有回傳來源 | 104 / 104 |
| 總時間 | 2133.65 秒 |
| 平均時間 | 20.52 秒 / 題 |

「有回傳來源」只代表檢索流程產生引用，不等於答案經人工判定完全正確。原始輸出曾包含找不到答案、內容不完整與模型表述差異，因此不應將這組數據解讀為準確率。

## 限制

- 執行硬體、Ollama 與模型版本未完整鎖定。
- 題目由開發者依展示法規整理，並非獨立第三方測試集。
- 沒有逐題雙人標註、引用一致性評分或統計信賴區間。
- 法規內容與模型行為日後可能改變，結果不可直接與新版比較。

## 重現

輸出預設寫入已忽略的 `artifacts/evaluation/`：

```bash
python scripts/evaluate_rag.py --limit 10
python scripts/evaluate_rag.py --output-dir artifacts/evaluation
```

可用 `--model` 與 `--ollama-base-url` 指定本機推論環境。
