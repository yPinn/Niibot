# Check-in Photocard 非破壞式原畫與疊圖契約

## 目標

原畫只保存影像內容；卡框、卡名、評級、稀有度與主題效果由共用 renderer 疊加。更換語系、主題或繪師時，不需要修改或重新烙字到原圖。

## 資產分層

```text
artwork/collections/
├─ catalog.json
└─ <collection-key>/<source-name>.<jpg|jpeg|png>

frontend/public/images/collections/
├─ integrity.json
└─ <collection-key>/<card-key>-r<revision>.webp
```

- `artwork/collections/` 是不公開的 source of truth；只存原始 JPEG／PNG 與 metadata catalog。
- `frontend/public/images/collections/` 只存可重建的 720 × 1080 WebP。
- collection key 使用小寫 kebab-case；card 與 source key 採 `<stage-name>-<兩位序號>`，同一成員以序號區分照片。
- `display_name` 保存成員藝名的正式大小寫，之後可作 DB seed／管理工具輸入；目前 renderer 仍從 event／DB snapshot 取得顯示文字。
- 正式衍生檔以檔名中的 `r<revision>` 固定身分。相同 revision 不得以不同原圖、framing 或內容覆寫。

## 原圖規格

- 接受內容與副檔名一致的單幀 JPG／JPEG／PNG，完整解碼前先套用 50 MP 安全上限。
- EXIF 方向在幾何計算前正規化；內嵌 ICC 轉為 sRGB；輸出不保留 EXIF、XMP 或其他非必要 metadata。
- PNG alpha 會保留。原圖永遠不搬移、不覆寫，也不加入卡框、文字、Logo 或評級。
- 常態新委託以 2:3、1440 × 2160 px、sRGB 為建議交付基準；這是合作品質規格，不是既有照片的硬性 ingest 門檻。
- runtime 目標為 FHD 畫面中的 720 × 1080 卡面，不要求 4K 衍生檔。

## Catalog 與 framing

每張卡在 `catalog.json` 保存：

- 穩定 `key`、原圖 `source`、公開 `revision`。
- 與檔名分離的 nullable `display_name`。
- `crop.mode` 與 0–1 正規化 `focal_point`。

預設使用 `cover`：保持比例，以 focal point 為中心計算最大 2:3 crop，再用 Lanczos 縮放；絕不拉伸。只有關鍵內容無法安全裁切時才使用 `contain`，完整保留原圖並以透明區域補足 2:3。

預覽報告會記錄實際 crop box、裁切比例與線性放大倍率。預設警示門檻為：

- 裁切面積超過 18%。
- 線性放大超過 1.15 倍。

## Preview 與正式 build

先執行：

```bash
npm run nb -- assets collections preview
```

輸出至 gitignored 的 `tasks/collection-assets-preview/`：

- 每張 720 × 1080 WebP，與正式輸出使用相同 framing／編碼。
- 每個 collection 一張 `contact-sheet.jpg`。
- `preview-report.json`，包含來源尺寸、crop box、裁切率、放大率與 warnings。

人工確認人物臉部、頭髮、帽沿、手部及辨識物件後，再執行：

```bash
npm run nb -- assets collections build
```

正式 build 會產生 WebP 與 `integrity.json`，記錄來源／輸出 SHA-256、尺寸、framing 與編碼參數。
可加入新的 card revision；已存在 revision 若來源、framing、輸出或 encoding contract 不同，會直接拒絕。

## Renderer 圖層

1. CSS 卡片容器與 2:3 幾何。
2. WebP 原畫衍生圖。
3. SVG `clipPath`、mask、卡框與角飾。
4. CSS／SVG 稀有度材質、光效與主題效果。
5. HTML 文字：卡號、卡名、系列、評級與署名。
6. 可存取性文字與互動狀態。

任何疊圖都不可反向寫入原畫。若 framing 不合適，只調整該卡的 focal point 或 crop mode；已發布卡片則提高 revision。

## 尺寸與實體預留

| 用途                  | 輸出                               |
| --------------------- | ---------------------------------- |
| 一般卡面／FHD Overlay | 720 × 1080 px                      |
| 常態新委託原畫        | 建議至少 1440 × 2160 px            |
| 55 × 85 mm 小卡送印   | 含 3 mm 出血約 61 × 91 mm、300 ppi |

實體送印時，應由原畫、SVG 卡框與資料文字重新合成承印廠指定的 PDF／PNG；扁平送印檔不是永久原畫資產。若未來的承印尺寸或出血模板需要更多邊緣內容，應回到原圖與 framing metadata 重新輸出，不放大 WebP 當印刷母檔。

參考：

- [Adobe：300 ppi 印刷解析度](https://helpx.adobe.com/photoshop/desktop/crop-resize-transform/resize-adjust-resolution/resolution-specs-for-printing-images.html)
- [55 × 85 mm photocard 與 3 mm 出血](https://photocard.ai/guides/kpop-photocard-size)
