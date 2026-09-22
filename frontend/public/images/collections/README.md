# Generated check-in collection assets

此目錄只存放由 `artwork/collections/catalog.json` 產生的公開 WebP；不要手動編輯，也不要放入 JPEG／PNG 原圖。

```text
<collection-key>/<card-key>-r<revision>.webp
integrity.json
```

前端同源 URL：

```text
/images/collections/<collection-key>/<card-key>-r<revision>.webp
```

請先執行 `npm run nb -- assets collections preview` 檢查裁切，再執行 `npm run nb -- assets collections build`。完整流程請參考 [`artwork/collections/README.md`](../../../../artwork/collections/README.md)。
