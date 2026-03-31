(function () {
  function renderTemplate(raw, context) {
    return (raw || '').replace(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g, function (_, key) {
      return Object.prototype.hasOwnProperty.call(context, key) ? (context[key] || '') : '';
    });
  }

  function byId(id) {
    return document.getElementById(id);
  }

  function updatePreview() {
    var preview = byId('parcel-dynamic-preview');
    if (!preview) {
      return;
    }
    var sample = {
      recipient_name: 'Nguyen Van A',
      parcel_count: '3',
      primary_sender: 'Viettel Post',
      company_name: 'F88',
      confirm_url: 'https://chungtu.f88.vn/admindocuments/parcel-receipts/batches/confirm/sample-token'
    };
    var titleInput = byId('id_title_template');
    var bodyInput = byId('id_body_template');
    var buttonInput = byId('id_button_text');
    var imageInput = byId('id_hero_image_url');
    var buttonBgInput = byId('id_button_bg_color');
    var buttonTextInput = byId('id_button_text_color');
    var borderInput = byId('id_card_border_color');

    var title = renderTemplate(titleInput ? titleInput.value : '', sample);
    var body = renderTemplate(bodyInput ? bodyInput.value : '', sample);
    var buttonText = renderTemplate(buttonInput ? buttonInput.value : '', sample);
    var image = imageInput && imageInput.value ? imageInput.value : preview.dataset.defaultImage;

    byId('parcel-preview-title').textContent = title;
    byId('parcel-preview-body').textContent = body;
    byId('parcel-preview-button-text').textContent = buttonText;
    byId('parcel-preview-image').src = image;
    preview.style.borderColor = borderInput && borderInput.value ? borderInput.value : '#DADDE1';
    byId('parcel-preview-button').style.background = buttonBgInput && buttonBgInput.value ? buttonBgInput.value : '#16A34A';
    byId('parcel-preview-button').style.color = buttonTextInput && buttonTextInput.value ? buttonTextInput.value : '#FFFFFF';
  }

  document.addEventListener('DOMContentLoaded', function () {
    [
      'id_title_template',
      'id_body_template',
      'id_button_text',
      'id_hero_image_url',
      'id_button_bg_color',
      'id_button_text_color',
      'id_card_border_color'
    ].forEach(function (id) {
      var field = byId(id);
      if (field) {
        field.addEventListener('input', updatePreview);
        field.addEventListener('change', updatePreview);
      }
    });
    updatePreview();
  });
})();
