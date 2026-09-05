(function () {
  const STATES = {
    ready: {
      label: 'Ready to scan',
      icon: 'qr_code_scanner',
      panel: 'border-blue-300 bg-blue-50 text-blue-900',
      iconBox: 'bg-blue-600 text-white',
    },
    reading: {
      label: 'Reading',
      icon: 'progress_activity',
      panel: 'border-amber-300 bg-amber-50 text-amber-900',
      iconBox: 'bg-amber-500 text-white',
      spin: true,
    },
    accepted: {
      label: 'Accepted',
      icon: 'check_circle',
      panel: 'border-emerald-400 bg-emerald-50 text-emerald-900',
      iconBox: 'bg-emerald-600 text-white',
      sound: 'accepted',
    },
    rejected: {
      label: 'Rejected',
      icon: 'cancel',
      panel: 'border-red-400 bg-red-50 text-red-900',
      iconBox: 'bg-red-600 text-white',
      sound: 'rejected',
    },
    duplicate: {
      label: 'Duplicate',
      icon: 'content_copy',
      panel: 'border-violet-400 bg-violet-50 text-violet-900',
      iconBox: 'bg-violet-600 text-white',
      sound: 'duplicate',
    },
  };

  let audioContext;

  function unlockAudio() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    audioContext = audioContext || new AudioContext();
    if (audioContext.state === 'suspended') audioContext.resume().catch(function () {});
  }

  window.addEventListener('keydown', unlockAudio, { capture: true });
  window.addEventListener('pointerdown', unlockAudio, { capture: true });

  function tone(frequency, start, duration, volume) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    unlockAudio();
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = 'sine';
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(volume, audioContext.currentTime + start);
    gain.gain.exponentialRampToValueAtTime(0.001, audioContext.currentTime + start + duration);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(audioContext.currentTime + start);
    oscillator.stop(audioContext.currentTime + start + duration);
  }

  function playSound(kind) {
    try {
      if (kind === 'accepted') {
        tone(880, 0, 0.1, 0.12);
        tone(1175, 0.1, 0.12, 0.1);
      } else if (kind === 'duplicate') {
        tone(440, 0, 0.09, 0.12);
        tone(440, 0.14, 0.09, 0.12);
      } else if (kind === 'rejected') {
        tone(220, 0, 0.24, 0.14);
      }
    } catch (error) {
      // Audio is supplementary; state text and icons remain authoritative.
    }
  }

  class ScanStateMachine {
    constructor(root, options) {
      this.root = typeof root === 'string' ? document.getElementById(root) : root;
      this.options = options || {};
      this.state = 'ready';
      this.resetTimer = null;
      this.render('ready', this.options.readyText || 'Waiting for scanner input');
    }

    render(name, detail) {
      if (!this.root || !STATES[name]) return;
      const config = STATES[name];
      this.state = name;
      this.root.className = 'scan-state flex items-center gap-4 rounded-2xl border-2 px-5 py-4 shadow-sm transition-all ' + config.panel;
      const icon = this.root.querySelector('[data-scan-icon]');
      const label = this.root.querySelector('[data-scan-label]');
      const message = this.root.querySelector('[data-scan-detail]');
      if (icon) {
        icon.textContent = config.icon;
        icon.parentElement.className = 'flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ' + config.iconBox;
        icon.className = 'material-symbols-outlined text-3xl' + (config.spin ? ' animate-spin' : '');
      }
      if (label) label.textContent = config.label;
      if (message) message.textContent = detail || config.label;
      this.root.dataset.scanState = name;
      if (config.sound) playSound(config.sound);
    }

    set(name, detail, resetDelay) {
      window.clearTimeout(this.resetTimer);
      this.render(name, detail);
      if (resetDelay) {
        this.resetTimer = window.setTimeout(() => this.ready(), resetDelay);
      }
    }

    ready(detail) { this.set('ready', detail || this.options.readyText || 'Waiting for scanner input'); }
    reading(detail) { this.set('reading', detail || 'Validating scanned data…'); }
    accepted(detail, delay) { this.set('accepted', detail || 'Scan accepted', delay); }
    rejected(detail, delay) { this.set('rejected', detail || 'Scan rejected', delay); }
    duplicate(detail, delay) { this.set('duplicate', detail || 'This scan was already recorded', delay); }

    keepFocus(getInput) {
      const focus = () => {
        if (document.hidden || this.state === 'reading') return;
        const active = document.activeElement;
        const editingElsewhere = active && active !== document.body
          && /^(INPUT|TEXTAREA|SELECT)$/.test(active.tagName)
          && active !== getInput();
        if (editingElsewhere) return;
        const input = getInput();
        if (input && !input.disabled) input.focus({ preventScroll: true });
      };
      window.setTimeout(focus, 0);
      window.addEventListener('focus', focus);
      document.addEventListener('visibilitychange', focus);
      document.addEventListener('pointerup', () => window.setTimeout(focus, 0));
      this.focusTimer = window.setInterval(focus, 800);
    }
  }

  window.ScanStateMachine = ScanStateMachine;
})();
