import os
import fitz  # PyMuPDF

# 使用相對路徑取得專案根目錄，使腳本在任何電腦上都能運行
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)

pdf_path = os.path.join(project_root, "frontend", "public", "Smart_SCU_Law_Navigator＿1.pdf")
output_dir = os.path.join(project_root, "frontend", "public", "slides")

# 確保輸出目錄存在且為空 (防範舊簡報圖片殘留)
import shutil
if os.path.exists(output_dir):
    try:
        shutil.rmtree(output_dir)
    except Exception as e:
        print(f"清空舊目錄失敗: {e}")
os.makedirs(output_dir, exist_ok=True)

# 開啟 PDF 檔案
doc = fitz.open(pdf_path)
print(f"總頁數: {len(doc)}")

for i, page in enumerate(doc):
    # 設定解析度 (DPI 200，保證清晰度)
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    
    # 輸出檔名例如 slide_1.png
    output_path = os.path.join(output_dir, f"slide_{i + 1}.png")
    pix.save(output_path)
    print(f"已導出第 {i + 1} 頁 -> {output_path}")

print("轉換完成！")
doc.close()
