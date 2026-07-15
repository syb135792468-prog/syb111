/**
 * assets/animation/helper_functions.js
 * 视频播放器辅助函数（语法高亮、代码渲染、变量面板、语音合成）
 * 从 video_agent.py 提取，便于维护和复用
 */

// === 语法高亮 ===
function highlightSyntax(code) {
  var escaped = code.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  escaped = escaped.replace(/(#.*)$/gm, '<span class="cmt">$1</span>');
  escaped = escaped.replace(/(\"\"\"[\s\S]*?\"\"\"|'''[\s\S]*?'''|"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')/g, '<span class="str">$1</span>');
  escaped = escaped.replace(/\b(def|class|if|elif|else|for|while|return|import|from|try|except|finally|with|as|yield|lambda|pass|break|continue|raise|and|or|not|in|is|True|False|None|self|print)\b/g, function(m) {
    if (m === 'self') return '<span class="self">' + m + '</span>';
    return '<span class="kw">' + m + '</span>';
  });
  escaped = escaped.replace(/\b(\d+\.?\d*)\b/g, '<span class="num">$1</span>');
  return escaped;
}

function renderCode(code, highlights) {
  var lines = code.split('\n');
  var html = '';
  for (var i = 0; i < lines.length; i++) {
    var hl = highlights && highlights.indexOf(i + 1) >= 0 ? ' highlight' : '';
    html += '<div class="code-line' + hl + '">';
    html += '<span class="line-num">' + (i+1) + '</span>';
    html += highlightSyntax(lines[i]);
    html += '</div>';
  }
  document.getElementById('codeDisplay').innerHTML = html;
}

function showVar(name, value) {
  var container = document.getElementById('varContainer');
  var existing = document.getElementById('var-' + name);
  if (existing) {
    var valEl = existing.querySelector('.var-value');
    valEl.textContent = value;
    gsap.fromTo(valEl, {backgroundColor: 'rgba(251,191,36,0.4)'}, {backgroundColor: 'transparent', duration: 0.8});
  } else {
    var card = document.createElement('div');
    card.className = 'var-card';
    card.id = 'var-' + name;
    card.innerHTML = '<span class="var-name">' + name + '</span> = <span class="var-value">' + value + '</span>';
    container.appendChild(card);
    gsap.from(card, {autoAlpha: 0, x: -20, duration: 0.4, ease: 'power2.out'});
  }
}

function clearVars() {
  document.getElementById('varContainer').innerHTML = '';
}

function updateStepDisplay(step) {
  var total = document.querySelectorAll('.step-dot').length || 1;
  document.getElementById('stepCounter').textContent = '第 ' + step + ' 步 / 共 ' + total + ' 步';
  var dots = document.querySelectorAll('.step-dot');
  dots.forEach(function(dot, i) {
    dot.className = 'step-dot';
    if (i < step - 1) dot.classList.add('done');
    if (i === step - 1) dot.classList.add('active');
  });
}

function speak(text, callback) {
  if (!('speechSynthesis' in window)) {
    if (callback) setTimeout(callback, 2000);
    return;
  }
  window.speechSynthesis.cancel();
  var u = new SpeechSynthesisUtterance(text);
  u.lang = 'zh-CN';
  u.rate = window.speechRate || 1.0;
  if (callback) u.onend = callback;
  window.speechSynthesis.speak(u);
  var bar = document.getElementById('subtitleBar');
  if (bar) {
    bar.textContent = text;
    bar.style.display = 'block';
  }
}

function updateProgress(percent) {
  document.getElementById('progressFill').style.width = percent + '%';
}