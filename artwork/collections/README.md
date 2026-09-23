# Check-in collection originals

這裡保存 JPEG／PNG 原圖與單一 `catalog.json`。前端不會直接公開此目錄，轉換流程也不會搬移、覆寫或在原圖上加入卡框與文字。

## 目錄

```text
artwork/collections/
├─ catalog.json
├─ <collection-key>/
│  ├─ <source-name>.jpg
│  └─ <source-name>.png
└─ ...
```

- 目錄與來源檔名使用小寫英數及連字號；collection 目錄只保留一層。
- 卡片檔名採 `<stage-name>-<兩位序號>`，例如 `karina-01.jpg`；同一成員以序號區分照片。
- 檔名只作機器識別，不會直接成為畫面文字。
- collection／卡片的顯示大小寫、revision 與裁切方式統一由 `catalog.json` 管理。
- 原圖可為不同直式比例；腳本會先套用 EXIF 方向，再依 focal point 等比例裁成 2:3，不會拉伸。
- 常態新委託仍以 2:3、1440 × 2160 px、sRGB 為建議交付規格；既有素材不因未達此尺寸而直接拒絕。

## Catalog 欄位

```json
{
  "key": "karina-01",
  "source": "karina-01.jpg",
  "revision": 1,
  "display_name": "Karina",
  "crop": {
    "mode": "cover",
    "focal_point": { "x": 0.5, "y": 0.42 }
  }
}
```

- `key`：以成員藝名與兩位序號組成的穩定小寫 kebab-case 機器識別。
- `source`：同一 collection 目錄內的原圖檔名。
- `display_name`：畫面使用的成員藝名與正式大小寫；身分尚未確認時才保留 `null`。
- `revision`：公開衍生檔 revision。已 build 的原圖或 framing 有變更時遞增。
- `crop.mode`：預設 `cover`；無法安全裁切的例外才使用透明留邊的 `contain`。
- `focal_point`：原圖正規化座標，左上為 `0, 0`、右下為 `1, 1`。

## 預覽與 build

先產生與正式卡面相同的 720 × 1080 裁切預覽：

```bash
npm run nb -- assets collections preview
```

預覽位於 `tasks/collection-assets-preview/`，包含每張 WebP、各 collection 的 contact sheet 與
`preview-report.json`。預設在裁切超過 18% 或線性放大超過 1.15 倍時提出警示。

確認 framing 後才產生正式 immutable 衍生檔：

```bash
npm run nb -- assets collections build
```

正式輸出位於 `frontend/public/images/collections/`。同一 `collection-key/card-key-rN.webp` 不可覆寫；修改原圖或裁切設定時必須提高 `revision`。
