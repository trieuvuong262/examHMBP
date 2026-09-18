document.addEventListener('DOMContentLoaded', function () {
  const cfg = window.JP_LUCKYSPIN || {};
  const spinBtn = document.getElementById('spinBtn');
  const spinBtnLabel = spinBtn && spinBtn.querySelector('.jp-luckyspin-btn-label');
  const remainingEl = document.getElementById('spin-remaining');
  const stage = document.getElementById('spinStage');
  const statusEl = document.getElementById('spinStatus');
  const slots = [
    document.querySelector('#slot1 .jp-luckyspin-numbers'),
    document.querySelector('#slot2 .jp-luckyspin-numbers'),
    document.querySelector('#slot3 .jp-luckyspin-numbers'),
  ];
  if (!spinBtn || slots.some(function (s) { return !s; })) return;

  const numbersCount = 10;
  const positions = [0, 0, 0];
  const spinning = [false, false, false];
  let isSpinning = false;
  let numberStr = '';

  function setBtnText(text) {
    if (spinBtnLabel) spinBtnLabel.textContent = text;
    else spinBtn.innerText = text;
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function setStageSpinning(on) {
    if (stage) stage.classList.toggle('is-spinning', !!on);
  }

  function itemHeight() {
    return slots[0].parentElement.getBoundingClientRect().height || 120;
  }

  function setPlaceholder(slot) {
    slot.innerHTML = '?';
    slot.style.transform = 'translateY(0)';
  }

  function setNumbers(slot) {
    slot.innerHTML = '';
    for (let i = 0; i < numbersCount; i += 1) {
      const div = document.createElement('div');
      div.textContent = i;
      slot.appendChild(div);
    }
  }

  slots.forEach(setPlaceholder);

  function animateSpin() {
    const h = itemHeight();
    slots.forEach(function (slot, idx) {
      if (spinning[idx]) {
        positions[idx] -= 20;
        if (positions[idx] <= -h * numbersCount) positions[idx] = 0;
        slot.style.transition = 'none';
        slot.style.transform = 'translateY(' + positions[idx] + 'px)';
      }
    });
    if (spinning.some(Boolean)) requestAnimationFrame(animateSpin);
  }

  function stopSlot(slotIdx, finalNumber) {
    spinning[slotIdx] = false;
    const h = itemHeight();
    const finalPos = -finalNumber * h;
    slots[slotIdx].style.transition = 'transform 1s cubic-bezier(0.22, 0.61, 0.36, 1)';
    slots[slotIdx].style.transform = 'translateY(' + finalPos + 'px)';
    positions[slotIdx] = finalPos;
  }

  function stopAllSlotsImmediate() {
    spinning[0] = spinning[1] = spinning[2] = false;
  }

  async function startSpin() {
    spinBtn.disabled = true;
    isSpinning = true;
    setStageSpinning(true);
    setStatus('Đang quay…');
    setBtnText('Dừng lại');
    slots.forEach(setNumbers);
    positions.fill(0);
    spinning[0] = spinning[1] = spinning[2] = true;
    animateSpin();

    try {
      const resLucky = await fetch(cfg.checkUrl);
      const dataLucky = await resLucky.json();
      if (dataLucky.has_lucky && dataLucky.number) {
        numberStr = String(dataLucky.number);
      } else {
        const resSpin = await fetch(cfg.spinUrl);
        const dataSpin = await resSpin.json();
        numberStr = String(dataSpin.result || dataSpin.number || '');
        if (remainingEl && typeof dataSpin.remaining === 'number') {
          remainingEl.textContent = dataSpin.remaining;
        }
      }
      numberStr = numberStr.padStart(3, '0');
      spinBtn.disabled = false;
      setStatus('Bấm dừng');
    } catch (err) {
      alert('Lỗi kết nối, thử lại!');
      stopAllSlotsImmediate();
      slots.forEach(setPlaceholder);
      setBtnText('Quay Số');
      setStatus('Sẵn sàng');
      setStageSpinning(false);
      spinBtn.disabled = false;
      isSpinning = false;
    }
  }

  function stopSpinSequence() {
    spinBtn.disabled = true;
    setStatus('Đang dừng…');
    const hundreds = parseInt(numberStr[0], 10) || 0;
    const tens = parseInt(numberStr[1], 10) || 0;
    const ones = parseInt(numberStr[2], 10) || 0;
    setTimeout(function () { stopSlot(0, hundreds); }, 1000);
    setTimeout(function () { stopSlot(1, tens); }, 2000);
    setTimeout(function () {
      stopSlot(2, ones);
      isSpinning = false;
      setBtnText('Quay Số');
      spinBtn.disabled = false;
      setTimeout(function () {
        setStageSpinning(false);
        setStatus('Sẵn sàng');
        showPopup(numberStr);
      }, 1500);
    }, 3000);
  }

  spinBtn.addEventListener('click', function () {
    spinBtn.classList.add('clicked');
    setTimeout(function () { spinBtn.classList.remove('clicked'); }, 500);
    if (!isSpinning) startSpin();
    else if (!spinBtn.disabled) {
      spinBtn.disabled = true;
      stopSpinSequence();
    }
  });

  /* Fullscreen */
  const fsRoot = document.getElementById('spinFullscreenRoot');
  const fsBtn = document.getElementById('spinFullscreenBtn');
  const fsIcon = fsBtn && fsBtn.querySelector('i');
  const fsLabel = fsBtn && fsBtn.querySelector('.jp-luckyspin-fs-label');

  function isNativeFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement);
  }

  function isFullscreenActive() {
    return isNativeFullscreen() || (fsRoot && fsRoot.classList.contains('is-immersive'));
  }

  function syncFullscreenUi() {
    const on = isFullscreenActive();
    if (fsBtn) {
      fsBtn.setAttribute('aria-pressed', on ? 'true' : 'false');
      fsBtn.title = on ? 'Thoát toàn màn hình' : 'Toàn màn hình';
    }
    if (fsIcon) {
      fsIcon.className = on ? 'bi bi-fullscreen-exit' : 'bi bi-fullscreen';
    }
    if (fsLabel) {
      fsLabel.textContent = on ? 'Thoát' : 'Toàn màn hình';
    }
    document.body.classList.toggle('jp-luckyspin-no-scroll', !!(fsRoot && fsRoot.classList.contains('is-immersive')));
  }

  async function enterFullscreen() {
    if (!fsRoot) return;
    try {
      if (fsRoot.requestFullscreen) await fsRoot.requestFullscreen();
      else if (fsRoot.webkitRequestFullscreen) fsRoot.webkitRequestFullscreen();
      else fsRoot.classList.add('is-immersive');
    } catch (err) {
      fsRoot.classList.add('is-immersive');
    }
    syncFullscreenUi();
  }

  async function exitFullscreen() {
    try {
      if (isNativeFullscreen()) {
        if (document.exitFullscreen) await document.exitFullscreen();
        else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
      }
    } catch (err) { /* ignore */ }
    if (fsRoot) fsRoot.classList.remove('is-immersive');
    syncFullscreenUi();
  }

  if (fsBtn && fsRoot) {
    fsBtn.addEventListener('click', function () {
      if (isFullscreenActive()) exitFullscreen();
      else enterFullscreen();
    });
    document.addEventListener('fullscreenchange', syncFullscreenUi);
    document.addEventListener('webkitfullscreenchange', syncFullscreenUi);
  }

  document.addEventListener('keydown', function (event) {
    const popup = document.getElementById('resultPopup');
    const open = popup && popup.classList.contains('is-open');
    if (event.code === 'Space') {
      event.preventDefault();
      if (open) return;
      if (!spinBtn.disabled) spinBtn.click();
    }
    if (event.code === 'Enter' && open) {
      event.preventDefault();
      closePopup();
    }
    if ((event.key === 'f' || event.key === 'F') && !open && !event.ctrlKey && !event.metaKey && !event.altKey) {
      const tag = (event.target && event.target.tagName) || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      event.preventDefault();
      if (fsBtn) fsBtn.click();
    }
  });
});

function showPopup(numberStr) {
  const popup = document.getElementById('resultPopup');
  const num = document.getElementById('popupNumber');
  if (num) num.textContent = numberStr;
  if (popup) popup.classList.add('is-open');
  if (window.confetti) {
    const canvas = document.getElementById('confettiCanvas');
    const fire = canvas ? confetti.create(canvas, { resize: true, useWorker: true }) : confetti;
    fire({
      particleCount: 180,
      spread: 70,
      startVelocity: 45,
      origin: { y: 0.65 },
      colors: ['#dc2626', '#fbbf24', '#ef4444', '#fde68a', '#ffffff'],
    });
    setTimeout(function () {
      fire({
        particleCount: 120,
        angle: 60,
        spread: 55,
        origin: { x: 0, y: 0.7 },
        colors: ['#dc2626', '#fbbf24', '#ffffff'],
      });
      fire({
        particleCount: 120,
        angle: 120,
        spread: 55,
        origin: { x: 1, y: 0.7 },
        colors: ['#dc2626', '#fbbf24', '#ffffff'],
      });
    }, 220);
  }
}

function closePopup() {
  const popup = document.getElementById('resultPopup');
  if (popup) popup.classList.remove('is-open');
}
