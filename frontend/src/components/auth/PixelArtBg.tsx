import React from 'react'

/*
 * Glassmorphism background characters for the auth screen.
 * Cute rounded SVG illustrations with translucent, glowing style:
 *   1. A smiling laptop with scrolling code on screen
 *   2. A cute robot with blinking eyes and antenna glow
 *
 * Dark background + colorful blobs + glass card aesthetic.
 */

// ── Laptop with scrolling code ──────────────────────────────────
const ComputerSVG: React.FC = () => (
  <svg width="160" height="140" viewBox="0 0 160 140" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Shadow */}
    <ellipse cx="80" cy="132" rx="50" ry="6" fill="rgba(0,0,0,0.3)" />

    {/* Screen body */}
    <rect x="20" y="10" width="120" height="85" rx="10" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5" />
    <rect x="28" y="18" width="104" height="68" rx="6" fill="rgba(0,0,0,0.5)" />

    {/* Code lines on screen (animated) */}
    <g className="char-code-scroll">
      <rect x="36" y="28" width="40" height="4" rx="2" fill="#c77dff" opacity="0.8" />
      <rect x="36" y="36" width="65" height="4" rx="2" fill="#00b4d8" opacity="0.7" />
      <rect x="36" y="44" width="30" height="4" rx="2" fill="#06d6a0" opacity="0.7" />
      <rect x="36" y="52" width="55" height="4" rx="2" fill="#f72585" opacity="0.6" />
      <rect x="36" y="60" width="45" height="4" rx="2" fill="#c77dff" opacity="0.7" />
      <rect x="36" y="68" width="70" height="4" rx="2" fill="#00b4d8" opacity="0.6" />
      <rect x="36" y="76" width="40" height="4" rx="2" fill="#c77dff" opacity="0.8" />
      <rect x="36" y="84" width="65" height="4" rx="2" fill="#00b4d8" opacity="0.7" />
    </g>

    {/* Screen glow */}
    <rect x="28" y="18" width="104" height="68" rx="6" fill="url(#screenGlow)" opacity="0.3" />

    {/* Hinge */}
    <rect x="50" y="95" width="60" height="4" rx="2" fill="rgba(255,255,255,0.1)" />

    {/* Keyboard base */}
    <path d="M25 99 L135 99 L145 125 Q145 130 140 130 L20 130 Q15 130 15 125 Z" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)" strokeWidth="1.5" />

    {/* Keyboard keys */}
    <rect x="35" y="104" width="12" height="6" rx="2" fill="rgba(255,255,255,0.08)" />
    <rect x="51" y="104" width="12" height="6" rx="2" fill="rgba(255,255,255,0.08)" />
    <rect x="67" y="104" width="12" height="6" rx="2" fill="rgba(255,255,255,0.08)" />
    <rect x="83" y="104" width="12" height="6" rx="2" fill="rgba(255,255,255,0.08)" />
    <rect x="99" y="104" width="12" height="6" rx="2" fill="rgba(255,255,255,0.08)" />
    <rect x="115" y="104" width="12" height="6" rx="2" fill="rgba(255,255,255,0.08)" />
    <rect x="40" y="114" width="80" height="6" rx="2" fill="rgba(255,255,255,0.08)" />

    {/* Power LED */}
    <circle cx="130" cy="92" r="2.5" fill="#06d6a0">
      <animate attributeName="opacity" values="0.4;1;0.4" dur="2s" repeatCount="indefinite" />
    </circle>

    {/* Cute face — eyes */}
    <circle cx="65" cy="13" r="2" fill="rgba(255,255,255,0.5)" />
    <circle cx="95" cy="13" r="2" fill="rgba(255,255,255,0.5)" />
    {/* Smile */}
    <path d="M72 15 Q80 19 88 15" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5" fill="none" strokeLinecap="round" />

    <defs>
      <linearGradient id="screenGlow" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stopColor="#7b2ff7" />
        <stop offset="100%" stopColor="#00b4d8" />
      </linearGradient>
    </defs>
  </svg>
)

// ── Cute robot ──────────────────────────────────────────────────
const RobotSVG: React.FC = () => (
  <svg width="110" height="140" viewBox="0 0 110 140" fill="none" xmlns="http://www.w3.org/2000/svg">
    {/* Shadow */}
    <ellipse cx="55" cy="134" rx="30" ry="5" fill="rgba(0,0,0,0.3)" />

    {/* Antenna */}
    <line x1="55" y1="8" x2="55" y2="22" stroke="rgba(255,255,255,0.3)" strokeWidth="2.5" strokeLinecap="round" />
    <circle className="char-antenna-pulse" cx="55" cy="8" r="3" fill="#c77dff">
      <animate attributeName="r" values="3;4.5;3" dur="2s" repeatCount="indefinite" />
      <animate attributeName="opacity" values="0.6;1;0.6" dur="2s" repeatCount="indefinite" />
    </circle>

    {/* Head */}
    <rect x="25" y="22" width="60" height="45" rx="14" fill="rgba(255,255,255,0.08)" stroke="rgba(255,255,255,0.15)" strokeWidth="1.5" />

    {/* Eyes */}
    <g className="char-eye-blink" style={{ transformOrigin: '42px 40px' }}>
      <circle cx="42" cy="40" r="7" fill="rgba(255,255,255,0.15)" />
      <circle cx="42" cy="40" r="4" fill="#c77dff" />
      <circle cx="40" cy="38" r="1.5" fill="rgba(255,255,255,0.8)" />
    </g>
    <g className="char-eye-blink" style={{ transformOrigin: '68px 40px' }}>
      <circle cx="68" cy="40" r="7" fill="rgba(255,255,255,0.15)" />
      <circle cx="68" cy="40" r="4" fill="#c77dff" />
      <circle cx="66" cy="38" r="1.5" fill="rgba(255,255,255,0.8)" />
    </g>

    {/* Cheeks */}
    <circle cx="32" cy="50" r="5" fill="#f72585" opacity="0.2" />
    <circle cx="78" cy="50" r="5" fill="#f72585" opacity="0.2" />

    {/* Mouth */}
    <path d="M45 54 Q55 60 65 54" stroke="rgba(255,255,255,0.3)" strokeWidth="2" fill="none" strokeLinecap="round" />

    {/* Neck */}
    <rect x="48" y="67" width="14" height="6" rx="3" fill="rgba(255,255,255,0.06)" />

    {/* Body */}
    <rect x="30" y="73" width="50" height="35" rx="12" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.12)" strokeWidth="1.5" />

    {/* Chest screen */}
    <rect x="40" y="80" width="30" height="16" rx="4" fill="rgba(0,0,0,0.4)" />
    <rect x="44" y="84" width="14" height="3" rx="1.5" fill="#c77dff" opacity="0.6" />
    <rect x="44" y="89" width="20" height="3" rx="1.5" fill="#00b4d8" opacity="0.5" />

    {/* Heart on chest */}
    <path d="M53 86 L55 89 L57 86 Q57 83 55 83 Q53 83 53 86Z" fill="#f72585" opacity="0.5">
      <animate attributeName="opacity" values="0.3;0.7;0.3" dur="2s" repeatCount="indefinite" />
    </path>

    {/* Arms */}
    <rect x="14" y="78" width="16" height="8" rx="4" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
    <rect x="80" y="78" width="16" height="8" rx="4" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />

    {/* Legs */}
    <rect x="38" y="108" width="12" height="18" rx="6" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
    <rect x="60" y="108" width="12" height="18" rx="6" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />

    {/* Feet */}
    <ellipse cx="44" cy="128" rx="10" ry="5" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
    <ellipse cx="66" cy="128" rx="10" ry="5" fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.1)" strokeWidth="1" />
  </svg>
)

// ── Main component ──────────────────────────────────────────────
const PixelArtBg: React.FC = () => {
  const codeSymbols = ['{ }', '</>', '( )', '=>', '[ ]', '#!']

  return (
    <div className="char-layer">
      {/* Computer — bottom right */}
      <div className="char-computer">
        <div className="char-computer-float">
          <ComputerSVG />
        </div>
      </div>

      {/* Robot — bottom left */}
      <div className="char-robot">
        <div className="char-robot-float">
          <RobotSVG />
        </div>
      </div>

      {/* Floating code symbols */}
      <div className="code-symbols">
        {codeSymbols.map((sym, i) => (
          <span key={i} className="code-symbol">{sym}</span>
        ))}
      </div>
    </div>
  )
}

export default PixelArtBg
