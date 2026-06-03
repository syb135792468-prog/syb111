import React from 'react'

const SkeletonCard: React.FC = () => {
  return (
    <div style={{
      border: '1px solid #e5e7eb',
      borderRadius: 12,
      overflow: 'hidden',
      background: '#fff',
      boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
    }}>
      {/* Header skeleton */}
      <div style={{
        background: 'linear-gradient(135deg, #e5e7eb, #d1d5db)',
        padding: '10px 14px',
        display: 'flex',
        alignItems: 'center',
        gap: 10,
      }}>
        <div style={{
          width: 24, height: 24, borderRadius: 6,
          background: 'rgba(255,255,255,0.4)',
          animation: 'pulse 1.5s ease-in-out infinite',
        }} />
        <div style={{ flex: 1 }}>
          <div style={{
            height: 14, width: '60%', borderRadius: 4,
            background: 'rgba(255,255,255,0.4)',
            animation: 'pulse 1.5s ease-in-out infinite',
          }} />
          <div style={{
            height: 10, width: '30%', borderRadius: 4,
            background: 'rgba(255,255,255,0.3)',
            marginTop: 4,
            animation: 'pulse 1.5s ease-in-out infinite 0.2s',
          }} />
        </div>
      </div>

      {/* Body skeleton */}
      <div style={{ padding: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>
        {[100, 85, 70].map((w, i) => (
          <div key={i} style={{
            height: 12, width: `${w}%`, borderRadius: 4,
            background: '#f3f4f6',
            animation: `pulse 1.5s ease-in-out infinite ${i * 0.15}s`,
          }} />
        ))}
      </div>
    </div>
  )
}

export default SkeletonCard
