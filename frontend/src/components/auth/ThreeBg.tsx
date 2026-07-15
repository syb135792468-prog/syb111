import React, { useRef, useEffect } from 'react'
import * as THREE from 'three'

/*
 * 3D particle background for the auth screen.
 * - Many bright glowing particles floating in 3D space
 * - Slow auto-rotation + mouse parallax
 * - Occasional shooting stars
 * - Bright blue / purple / pink palette
 */

const PARTICLE_COUNT = 800
const SHOOTING_STAR_INTERVAL = 2500

const ThreeBg: React.FC = () => {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    // ── Scene ────────────────────────────────────────────────
    const scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000)
    camera.position.z = 6

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true })
    renderer.setSize(window.innerWidth, window.innerHeight)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.setClearColor(0x000000, 0)
    container.appendChild(renderer.domElement)

    // ── Particles ────────────────────────────────────────────
    const positions = new Float32Array(PARTICLE_COUNT * 3)
    const colors = new Float32Array(PARTICLE_COUNT * 3)
    const sizes = new Float32Array(PARTICLE_COUNT)
    const speeds = new Float32Array(PARTICLE_COUNT)
    const phases = new Float32Array(PARTICLE_COUNT)

    const palette = [
      new THREE.Color('#a855f7'), // bright purple
      new THREE.Color('#d946ef'), // fuchsia
      new THREE.Color('#06b6d4'), // cyan
      new THREE.Color('#f472b6'), // pink
      new THREE.Color('#38bdf8'), // sky blue
      new THREE.Color('#c084fc'), // light purple
      new THREE.Color('#fb923c'), // orange accent
      new THREE.Color('#34d399'), // emerald accent
    ]

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      const i3 = i * 3
      positions[i3]     = (Math.random() - 0.5) * 25
      positions[i3 + 1] = (Math.random() - 0.5) * 18
      positions[i3 + 2] = (Math.random() - 0.5) * 15

      const color = palette[Math.floor(Math.random() * palette.length)]
      colors[i3]     = color.r
      colors[i3 + 1] = color.g
      colors[i3 + 2] = color.b

      sizes[i] = Math.random() * 5 + 2
      speeds[i] = Math.random() * 0.4 + 0.1
      phases[i] = Math.random() * Math.PI * 2
    }

    const particleGeometry = new THREE.BufferGeometry()
    particleGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3))
    particleGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    particleGeometry.setAttribute('size', new THREE.BufferAttribute(sizes, 1))

    const particleMaterial = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
      },
      vertexShader: `
        attribute float size;
        attribute vec3 color;
        varying vec3 vColor;
        varying float vAlpha;
        uniform float uTime;

        void main() {
          vColor = color;
          vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
          float depth = -mvPosition.z;
          // Brighter — higher base alpha
          vAlpha = smoothstep(15.0, 2.0, depth) * 0.95;
          // Pulsing
          float pulse = sin(uTime * 0.8 + position.x * 1.5 + position.y * 2.0) * 0.25 + 0.75;
          vAlpha *= pulse;
          // Larger points
          gl_PointSize = size * (250.0 / depth) * pulse;
          gl_Position = projectionMatrix * mvPosition;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        varying float vAlpha;

        void main() {
          float dist = length(gl_PointCoord - vec2(0.5));
          if (dist > 0.5) discard;
          // Soft glow with bright center
          float glow = 1.0 - smoothstep(0.0, 0.5, dist);
          glow = pow(glow, 1.2);
          // Bright center core
          float core = 1.0 - smoothstep(0.0, 0.15, dist);
          float brightness = glow + core * 0.5;
          gl_FragColor = vec4(vColor * 1.2, vAlpha * brightness);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    })

    const particles = new THREE.Points(particleGeometry, particleMaterial)
    scene.add(particles)

    // ── Shooting stars ───────────────────────────────────────
    const shootingStars: THREE.Mesh[] = []

    function createShootingStar() {
      const length = 1.5 + Math.random() * 2
      const geo = new THREE.PlaneGeometry(0.06, length)
      const hue = Math.random() * 0.3 + 0.55
      const mat = new THREE.MeshBasicMaterial({
        color: new THREE.Color().setHSL(hue, 0.9, 0.75),
        transparent: true,
        opacity: 0,
        blending: THREE.AdditiveBlending,
        side: THREE.DoubleSide,
      })
      const star = new THREE.Mesh(geo, mat)

      star.position.set(
        (Math.random() - 0.5) * 18,
        (Math.random() - 0.5) * 12 + 4,
        (Math.random() - 0.5) * 8 - 3
      )

      const angle = -Math.PI / 4 + (Math.random() - 0.5) * 0.6
      star.rotation.z = angle
      star.userData = {
        velocity: new THREE.Vector3(
          Math.cos(angle) * (0.12 + Math.random() * 0.08),
          Math.sin(angle) * (0.12 + Math.random() * 0.08),
          0
        ),
        life: 0,
        maxLife: 50 + Math.random() * 30,
      }

      scene.add(star)
      shootingStars.push(star)
    }

    // First shooting star sooner
    setTimeout(createShootingStar, 1000)
    const shootingStarTimer = setInterval(createShootingStar, SHOOTING_STAR_INTERVAL)

    // ── Mouse ────────────────────────────────────────────────
    let mouseX = 0
    let mouseY = 0

    const onMouseMove = (e: MouseEvent) => {
      mouseX = (e.clientX / window.innerWidth) * 2 - 1
      mouseY = -(e.clientY / window.innerHeight) * 2 + 1
    }
    window.addEventListener('mousemove', onMouseMove)

    // ── Resize ───────────────────────────────────────────────
    const onResize = () => {
      camera.aspect = window.innerWidth / window.innerHeight
      camera.updateProjectionMatrix()
      renderer.setSize(window.innerWidth, window.innerHeight)
    }
    window.addEventListener('resize', onResize)

    // ── Animate ──────────────────────────────────────────────
    let frameId: number
    let time = 0

    const animate = () => {
      frameId = requestAnimationFrame(animate)
      time += 0.016

      particleMaterial.uniforms.uTime.value = time

      // Slow auto-rotation
      particles.rotation.y += 0.0003
      particles.rotation.x += 0.0001

      // Mouse parallax — smooth
      const targetRX = mouseY * 0.12
      const targetRY = mouseX * 0.12
      particles.rotation.x += (targetRX - particles.rotation.x) * 0.015
      particles.rotation.y += (targetRY - particles.rotation.y) * 0.015

      // Gentle vertical float per particle
      const posArr = particleGeometry.attributes.position.array as Float32Array
      for (let i = 0; i < PARTICLE_COUNT; i++) {
        const i3 = i * 3
        posArr[i3 + 1] += Math.sin(time * speeds[i] + phases[i]) * 0.0015
        posArr[i3]     += Math.cos(time * speeds[i] * 0.5 + phases[i]) * 0.0005
      }
      particleGeometry.attributes.position.needsUpdate = true

      // Shooting stars
      for (let i = shootingStars.length - 1; i >= 0; i--) {
        const star = shootingStars[i]
        const ud = star.userData
        ud.life++

        const lifeRatio = ud.life / ud.maxLife
        const mat = star.material as THREE.MeshBasicMaterial
        if (lifeRatio < 0.15) {
          mat.opacity = lifeRatio / 0.15 * 0.9
        } else if (lifeRatio > 0.6) {
          mat.opacity = (1 - lifeRatio) / 0.4 * 0.9
        }

        star.position.add(ud.velocity)

        if (ud.life >= ud.maxLife) {
          scene.remove(star)
          star.geometry.dispose()
          mat.dispose()
          shootingStars.splice(i, 1)
        }
      }

      renderer.render(scene, camera)
    }
    animate()

    // ── Cleanup ──────────────────────────────────────────────
    return () => {
      cancelAnimationFrame(frameId)
      clearInterval(shootingStarTimer)
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('resize', onResize)
      container.removeChild(renderer.domElement)
      particleGeometry.dispose()
      particleMaterial.dispose()
      renderer.dispose()
    }
  }, [])

  return (
    <div
      ref={containerRef}
      className="three-bg-layer"
    />
  )
}

export default ThreeBg
