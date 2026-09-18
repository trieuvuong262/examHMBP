document.addEventListener('DOMContentLoaded', function () {
  const cfg = window.JP_LUCKYSPIN || {};
  const spinBtn = document.getElementById('spinBtn');
  const remainingEl = document.getElementById('spin-remaining');
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
    spinBtn.innerText = 'Dừng lại';
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
    } catch (err) {
      alert('Lỗi kết nối, thử lại!');
      stopAllSlotsImmediate();
      slots.forEach(setPlaceholder);
      spinBtn.innerText = 'Quay Số';
      spinBtn.disabled = false;
      isSpinning = false;
    }
  }

  function stopSpinSequence() {
    spinBtn.disabled = true;
    const hundreds = parseInt(numberStr[0], 10) || 0;
    const tens = parseInt(numberStr[1], 10) || 0;
    const ones = parseInt(numberStr[2], 10) || 0;
    setTimeout(function () { stopSlot(0, hundreds); }, 1000);
    setTimeout(function () { stopSlot(1, tens); }, 2000);
    setTimeout(function () {
      stopSlot(2, ones);
      isSpinning = false;
      spinBtn.innerText = 'Quay Số';
      spinBtn.disabled = false;
      setTimeout(function () { showPopup(numberStr); }, 1500);
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
    fire({ particleCount: 400, spread: 160, startVelocity: 70, origin: { y: 0.6 } });
  }
}

function closePopup() {
  const popup = document.getElementById('resultPopup');
  if (popup) popup.classList.remove('is-open');
}
