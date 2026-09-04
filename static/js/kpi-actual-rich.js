/**
 * Ô Đánh giá thực tế KPI — text + chèn/dán ảnh (upload NAS giống báo cáo).
 */
(function () {
  function csrfToken() {
    var input = document.querySelector('#kpi-detail-form input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function uploadBlob(uploadUrl, blob, fileName) {
    var formData = new FormData();
    formData.append('upload', blob, fileName || 'paste.png');
    return fetch(uploadUrl, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: formData,
    }).then(function (resp) {
      return resp.json().then(function (data) {
        if (!resp.ok || !data.url) {
          var msg = (data.error && data.error.message) || ('HTTP ' + resp.status);
          throw new Error(msg);
        }
        return data.url;
      });
    });
  }

  function insertImage(editor, url) {
    editor.focus();
    var img = document.createElement('img');
    img.src = url;
    img.alt = '';
    img.className = 'jp-kpi-inline-img';
    var sel = window.getSelection();
    if (sel && sel.rangeCount && editor.contains(sel.anchorNode)) {
      var range = sel.getRangeAt(0);
      range.deleteContents();
      range.insertNode(img);
      range.setStartAfter(img);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
    } else {
      editor.appendChild(img);
      editor.appendChild(document.createElement('br'));
    }
  }

  function syncOne(root) {
    var editor = root.querySelector('[data-kpi-rich-editor]');
    var input = root.querySelector('[data-kpi-rich-input]');
    if (!editor || !input) return;
    var html = (editor.innerHTML || '').trim();
    if (html === '<br>' || html === '<div><br></div>') html = '';
    input.value = html;
  }

  function syncAll(form) {
    form.querySelectorAll('[data-kpi-rich]').forEach(syncOne);
  }

  function bindRich(root, uploadUrl) {
    var editor = root.querySelector('[data-kpi-rich-editor]');
    var fileInput = root.querySelector('[data-kpi-rich-file]');
    if (!editor) return;

    function handleFiles(files) {
      Array.prototype.forEach.call(files || [], function (file) {
        if (!file || !(file.type || '').startsWith('image/')) return;
        uploadBlob(uploadUrl, file, file.name || 'image.png')
          .then(function (url) {
            insertImage(editor, url);
            syncOne(root);
          })
          .catch(function (err) {
            window.alert(err.message || 'Không upload được ảnh.');
          });
      });
    }

    editor.addEventListener('paste', function (event) {
      var items = event.clipboardData && event.clipboardData.items;
      if (!items) return;
      var imageItem = null;
      for (var i = 0; i < items.length; i += 1) {
        if (items[i].type && items[i].type.indexOf('image/') === 0) {
          imageItem = items[i];
          break;
        }
      }
      if (!imageItem) return;
      event.preventDefault();
      var blob = imageItem.getAsFile();
      if (!blob) return;
      uploadBlob(uploadUrl, blob, 'paste.png')
        .then(function (url) {
          insertImage(editor, url);
          syncOne(root);
        })
        .catch(function (err) {
          window.alert(err.message || 'Không upload được ảnh.');
        });
    });

    editor.addEventListener('drop', function (event) {
      var files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      var hasImage = false;
      for (var i = 0; i < files.length; i += 1) {
        if ((files[i].type || '').indexOf('image/') === 0) hasImage = true;
      }
      if (!hasImage) return;
      event.preventDefault();
      handleFiles(files);
    });

    editor.addEventListener('dragover', function (event) {
      event.preventDefault();
    });

    editor.addEventListener('input', function () {
      syncOne(root);
    });

    if (fileInput) {
      fileInput.addEventListener('change', function () {
        handleFiles(fileInput.files);
        fileInput.value = '';
      });
    }
  }

  function init() {
    var form = document.getElementById('kpi-detail-form');
    if (!form) return;
    var uploadUrl = form.getAttribute('data-kpi-upload-url') || '';
    if (!uploadUrl) return;

    form.querySelectorAll('[data-kpi-rich]').forEach(function (root) {
      bindRich(root, uploadUrl);
      syncOne(root);
    });

    form.addEventListener('submit', function () {
      syncAll(form);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
