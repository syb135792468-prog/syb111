/**
 * assets/animation/control_logic.js
 * 播放控制逻辑：绑定按钮事件，调用LLM定义的全局函数
 * 从 video_agent.py 提取，便于维护和复用
 */

// --- 开始按钮：调用LLM定义的startAnimation ---
document.getElementById('startButton').addEventListener('click', function() {
  if (typeof startAnimation === 'function') {
    startAnimation();
  } else {
    document.getElementById('startScreen').style.display = 'none';
    document.getElementById('playerScreen').style.display = 'block';
  }
});

// --- 播放/暂停：调用LLM定义的pauseAnimation/resumeAnimation ---
document.getElementById('playPauseButton').addEventListener('click', function() {
  if (window.isPlaying) {
    if (typeof pauseAnimation === 'function') pauseAnimation();
    document.getElementById('playPauseButton').textContent = '▶';
  } else {
    if (typeof resumeAnimation === 'function') resumeAnimation();
    document.getElementById('playPauseButton').textContent = '⏸';
  }
  window.isPlaying = !window.isPlaying;
});

// --- 重播：调用LLM定义的restartAnimation ---
document.getElementById('restartButton').addEventListener('click', function() {
  if (typeof restartAnimation === 'function') {
    restartAnimation();
  } else {
    window.speechSynthesis.cancel();
    window.isPlaying = false;
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('playerScreen').style.display = 'none';
    document.getElementById('startScreen').style.display = 'flex';
  }
});

// --- 进度条点击：调用LLM定义的seekTo ---
document.getElementById('progressBar').addEventListener('click', function(e) {
  var rect = e.currentTarget.getBoundingClientRect();
  var clickX = e.clientX - rect.left;
  var percent = Math.max(0, Math.min(100, (clickX / rect.width) * 100));
  document.getElementById('progressFill').style.width = percent + '%';
  if (typeof seekTo === 'function') seekTo(percent);
});

// --- 键盘快捷键 ---
document.addEventListener('keydown', function(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;
  switch (e.code) {
    case 'Space':
      e.preventDefault();
      document.getElementById('playPauseButton').click();
      break;
    case 'KeyR':
      e.preventDefault();
      document.getElementById('restartButton').click();
      break;
  }
});