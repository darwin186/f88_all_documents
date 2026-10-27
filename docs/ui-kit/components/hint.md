# Hint (icon thông tin giải thích điều kiện)

Icon `i` trong vòng tròn đặt cạnh nhãn của field. Hover hoặc bấm/focus vào icon sẽ hiện hộp giải thích. Dùng khi field bị khoá hoặc có quy tắc không hiển nhiên (ví dụ khi nào được đổi mã thùng).

```html
<span class="ui-hint" tabindex="0" role="button" aria-label="Điều kiện đổi mã thùng">
  <span class="ui-hint-icon" aria-hidden="true">i</span>
  <span class="ui-hint-pop" role="tooltip">
    <strong>Chỉ đổi được thùng khi:</strong>
    <ul><li>Chứng từ đã được nhận.</li><li>Thùng hiện tại không nằm ở đối tác.</li></ul>
  </span>
</span>
```

| Phần | Ghi chú |
|---|---|
| `.ui-hint` | Bọc ngoài, bắt buộc có `tabindex="0"` để bấm/bàn phím mở được hộp. |
| `.ui-hint-icon` | Vòng tròn 14px chứa chữ `i`. |
| `.ui-hint-pop` | Hộp nội dung rộng 240px, hiện khi hover/focus; nội dung ngắn, dạng danh sách điều kiện. |

Không cần JS. Đặt `.ui-hint` ở nơi không bị cha `overflow: hidden` cắt (hộp mở xuống dưới icon).

Ví dụ: nhãn "Mã thùng" trong drawer Duyệt chứng từ.
