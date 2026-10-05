/**
 * Bảng tiến độ — lưu ô inline (AJAX) + chèn/dán ảnh giống ô Đánh giá thực tế KPI.
 */
(function () {
  var root = document.getElementById('jp-tien-do');
  if (!root) return;

  var updateBase = root.getAttribute('data-cell-update-base') || '/tien-do/';
  var uploadUrl = root.getAttribute('data-image-upload-url') || '';

  function csrfToken() {
    var input = root.querySelector('input[name="csrfmiddlewaretoken"]');
    if (input && input.value) return input.value;
    var match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function post(url, data) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'X-CSRFToken': csrfToken(),
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: new URLSearchParams(data),
    }).then(function (resp) {
      return resp.json().then(function (json) {
        return { ok: resp.ok, data: json };
      });
    });
  }

  function uploadBlob(blob, fileName) {
    if (!uploadUrl) return Promise.reject(new Error('Không có quyền chèn ảnh.'));
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
          throw new Error((data.error && data.error.message) || ('HTTP ' + resp.status));
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
    img.className = 'jp-tien-do-inline-img';
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

  function readValue(editor, isRich) {
    if (!isRich) return editor.textContent.trim();
    var html = (editor.innerHTML || '').trim();
    if (html === '<br>' || html === '<div><br></div>') return '';
    return html;
  }

  function writeValue(editor, isRich, value) {
    if (isRich) editor.innerHTML = value;
    else editor.textContent = value;
  }

  function bindEditor(editor) {
    var cell = editor.closest('td');
    var row = editor.closest('tr');
    if (!cell || !row) return;

    var isRich = cell.getAttribute('data-rich') === '1';
    var column = cell.getAttribute('data-column');
    var itemId = row.getAttribute('data-item-id');
    var saveUrl = updateBase + itemId + '/sua-o/';
    var original = readValue(editor, isRich);
    var saving = false;

    function save() {
      var value = readValue(editor, isRich);
      if (saving || value === original) return;
      saving = true;
      post(saveUrl, { column: column, value: value })
        .then(function (res) {
          if (!res.ok) {
            window.alert(res.data.message || 'Lưu thất bại.');
            writeValue(editor, isRich, original);
          } else {
            original = res.data.value;
            if (document.activeElement !== editor) {
              writeValue(editor, isRich, original);
            }
          }
        })
        .catch(function () {
          window.alert('Lỗi kết nối.');
          writeValue(editor, isRich, original);
        })
        .then(function () {
          saving = false;
        });
    }

    editor.addEventListener('blur', save);

    if (!isRich) {
      editor.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
          event.preventDefault();
          editor.blur();
        }
      });
      return;
    }

    var fileInput = cell.querySelector('[data-td-file]');
    var button = cell.querySelector('.jp-cell-imgbtn');

    function handleBlob(blob, name) {
      if (button) button.classList.add('is-busy');
      uploadBlob(blob, name)
        .then(function (url) {
          insertImage(editor, url);
          save();
        })
        .catch(function (err) {
          window.alert(err.message || 'Không upload được ảnh.');
        })
        .then(function () {
          if (button) button.classList.remove('is-busy');
        });
    }

    function handleFiles(files) {
      Array.prototype.forEach.call(files || [], function (file) {
        if (!file || (file.type || '').indexOf('image/') !== 0) return;
        handleBlob(file, file.name || 'image.png');
      });
    }

    editor.addEventListener('paste', function (event) {
      var items = event.clipboardData && event.clipboardData.items;
      if (!items) return;
      for (var i = 0; i < items.length; i += 1) {
        if (items[i].type && items[i].type.indexOf('image/') === 0) {
          event.preventDefault();
          var blob = items[i].getAsFile();
          if (blob) handleBlob(blob, 'paste.png');
          return;
        }
      }
    });

    editor.addEventListener('dragover', function (event) {
      event.preventDefault();
    });

    editor.addEventListener('drop', function (event) {
      var files = event.dataTransfer && event.dataTransfer.files;
      if (!files || !files.length) return;
      event.preventDefault();
      handleFiles(files);
    });

    if (fileInput) {
      fileInput.addEventListener('change', function () {
        handleFiles(fileInput.files);
        fileInput.value = '';
      });
    }
  }

  root.querySelectorAll('[data-td-editor]').forEach(bindEditor);

  root.querySelectorAll('.jp-tested-toggle').forEach(function (box) {
    if (box.disabled) return;
    box.addEventListener('change', function () {
      var row = box.closest('tr');
      var id = row.getAttribute('data-item-id');
      post(updateBase + id + '/danh-dau-test/', {})
        .then(function (res) {
          if (!res.ok) {
            window.alert(res.data.message || 'Thất bại.');
            box.checked = !box.checked;
          } else {
            box.checked = res.data.is_tested;
          }
        })
        .catch(function () {
          window.alert('Lỗi kết nối.');
          box.checked = !box.checked;
        });
    });
  });
})();
