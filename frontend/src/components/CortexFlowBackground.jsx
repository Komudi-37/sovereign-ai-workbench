import React, { useEffect, useRef } from 'react';

/**
 * CortexFlowBackground
 * 
 * Cinematic, monochrome animated background inspired by data and neural flows.
 * - 100% local (Canvas 2D API + requestAnimationFrame)
 * - Zero external CDN dependencies, zero network requests
 * - pointer-events: none so it never blocks UI interactions
 * - Automatic cleanup on unmount
 * - Respects devicePixelRatio and prefers-reduced-motion
 */
function CortexFlowBackground() {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    // Check for reduced motion preference
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    let animationFrameId;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
      initPaths();
    };

    window.addEventListener('resize', handleResize);

    // Mouse tracking for subtle convergence / deflection
    let mouseX = width / 2;
    let mouseY = height / 2;
    let targetMouseX = width / 2;
    let targetMouseY = height / 2;

    const handleMouseMove = (e) => {
      targetMouseX = e.clientX;
      targetMouseY = e.clientY;
    };

    window.addEventListener('mousemove', handleMouseMove, { passive: true });

    // Stream paths & particle configuration
    let paths = [];
    const PATH_COUNT = Math.min(24, Math.max(12, Math.floor(width / 75)));
    const PARTICLES_PER_PATH = 3;

    function initPaths() {
      paths = [];
      const centerX = width * 0.55;
      const centerY = height * 0.48;

      for (let i = 0; i < PATH_COUNT; i++) {
        // Start points along outer perimeter (left, top, bottom, right)
        let startX, startY;
        const side = i % 4;
        if (side === 0) {
          // Left side
          startX = -20;
          startY = (i / PATH_COUNT) * height * 1.2 - height * 0.1;
        } else if (side === 1) {
          // Top side
          startX = (i / PATH_COUNT) * width * 1.2 - width * 0.1;
          startY = -20;
        } else if (side === 2) {
          // Bottom side
          startX = (i / PATH_COUNT) * width * 1.2 - width * 0.1;
          startY = height + 20;
        } else {
          // Right side
          startX = width + 20;
          startY = (i / PATH_COUNT) * height * 1.2 - height * 0.1;
        }

        // Control points for smooth bezier curve toward center
        const angle = Math.atan2(centerY - startY, centerX - startX);
        const distance = Math.hypot(centerX - startX, centerY - startY);
        
        const cp1x = startX + Math.cos(angle + (i % 2 === 0 ? 0.4 : -0.4)) * (distance * 0.4);
        const cp1y = startY + Math.sin(angle + (i % 2 === 0 ? 0.4 : -0.4)) * (distance * 0.4);
        
        const cp2x = centerX - Math.cos(angle) * (distance * 0.25) + ((i % 3) - 1) * 60;
        const cp2y = centerY - Math.sin(angle) * (distance * 0.25) + ((i % 5) - 2) * 50;

        // Exit or convergent focal point
        const endX = centerX + Math.cos(angle) * (width * 0.15);
        const endY = centerY + Math.sin(angle) * (height * 0.15);

        // Particles traveling along this curve
        const particles = [];
        for (let p = 0; p < PARTICLES_PER_PATH; p++) {
          particles.push({
            t: Math.random(),
            speed: 0.0006 + Math.random() * 0.0009,
            size: 1 + Math.random() * 1.5,
            opacity: 0.2 + Math.random() * 0.5,
          });
        }

        paths.push({
          startX, startY,
          cp1x, cp1y,
          cp2x, cp2y,
          endX, endY,
          particles,
          baseOpacity: 0.03 + (i % 3) * 0.015,
        });
      }
    }

    initPaths();

    // Cubic Bezier interpolation helper
    function getBezierPoint(t, p0, p1, p2, p3) {
      const cX = 3 * (p1.x - p0.x);
      const bX = 3 * (p2.x - p1.x) - cX;
      const aX = p3.x - p0.x - cX - bX;

      const cY = 3 * (p1.y - p0.y);
      const bY = 3 * (p2.y - p1.y) - cY;
      const aY = p3.y - p0.y - cY - bY;

      const x = (aX * Math.pow(t, 3)) + (bX * Math.pow(t, 2)) + (cX * t) + p0.x;
      const y = (aY * Math.pow(t, 3)) + (bY * Math.pow(t, 2)) + (cY * t) + p0.y;

      return { x, y };
    }

    let lastTime = performance.now();

    function render(currentTime) {
      const delta = Math.min(currentTime - lastTime, 64);
      lastTime = currentTime;

      // Smooth mouse interpolation
      mouseX += (targetMouseX - mouseX) * 0.04;
      mouseY += (targetMouseY - mouseY) * 0.04;

      // Clear with near-black base
      ctx.fillStyle = '#050505';
      ctx.fillRect(0, 0, width, height);

      // Draw subtle radial depth gradient from center
      const radialGradient = ctx.createRadialGradient(
        width * 0.52, height * 0.48, 20,
        width * 0.5, height * 0.5, Math.max(width, height) * 0.75
      );
      radialGradient.addColorStop(0, 'rgba(255, 255, 255, 0.015)');
      radialGradient.addColorStop(0.5, 'rgba(15, 15, 15, 0.4)');
      radialGradient.addColorStop(1, 'rgba(5, 5, 5, 1)');
      ctx.fillStyle = radialGradient;
      ctx.fillRect(0, 0, width, height);

      // Render flowing paths & particles
      const speedMultiplier = prefersReducedMotion ? 0.15 : 1.0;

      for (let i = 0; i < paths.length; i++) {
        const path = paths[i];
        const p0 = { x: path.startX, y: path.startY };
        
        // Subtle mouse influence on control points
        const mouseDist = Math.hypot(mouseX - path.cp1x, mouseY - path.cp1y);
        const mouseFactor = Math.max(0, 1 - mouseDist / 600) * 20;
        
        const p1 = { x: path.cp1x + ((mouseX - width / 2) * 0.03) + mouseFactor, y: path.cp1y + ((mouseY - height / 2) * 0.03) };
        const p2 = { x: path.cp2x + ((mouseX - width / 2) * 0.015), y: path.cp2y + ((mouseY - height / 2) * 0.015) };
        const p3 = { x: path.endX, y: path.endY };

        // Draw curved path line
        ctx.beginPath();
        ctx.moveTo(p0.x, p0.y);
        ctx.bezierCurveTo(p1.x, p1.y, p2.x, p2.y, p3.x, p3.y);
        ctx.strokeStyle = `rgba(255, 255, 255, ${path.baseOpacity})`;
        ctx.lineWidth = 1;
        ctx.stroke();

        // Draw animated particles along path
        for (let p = 0; p < path.particles.length; p++) {
          const pt = path.particles[p];
          pt.t += pt.speed * (delta / 16) * speedMultiplier;
          if (pt.t > 1) pt.t = 0;

          const pos = getBezierPoint(pt.t, p0, p1, p2, p3);

          // Fade in at start, fade out near center convergence
          let alpha = pt.opacity;
          if (pt.t < 0.15) alpha *= (pt.t / 0.15);
          if (pt.t > 0.8) alpha *= ((1 - pt.t) / 0.2);

          // Particle point
          ctx.beginPath();
          ctx.arc(pos.x, pos.y, pt.size, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255, 255, 255, ${alpha * 0.75})`;
          ctx.fill();

          // Particle subtle faint tail
          if (pt.t > 0.02) {
            const prevPos = getBezierPoint(Math.max(0, pt.t - 0.018), p0, p1, p2, p3);
            ctx.beginPath();
            ctx.moveTo(pos.x, pos.y);
            ctx.lineTo(prevPos.x, prevPos.y);
            ctx.strokeStyle = `rgba(255, 255, 255, ${alpha * 0.25})`;
            ctx.lineWidth = pt.size * 0.8;
            ctx.stroke();
          }
        }
      }

      animationFrameId = requestAnimationFrame(render);
    }

    animationFrameId = requestAnimationFrame(render);

    return () => {
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('mousemove', handleMouseMove);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <div className="cortex-background-wrapper" aria-hidden="true">
      <div className="cortex-radial-pattern" />
      <canvas
        ref={canvasRef}
        className="cortex-flow-canvas"
      />
    </div>
  );
}

export default CortexFlowBackground;
