import React, { useEffect, useRef } from 'react';

export const BlueprintGrid = ({ showParticles = true, dark = false }) => {
  const canvasRef = useRef(null);

  useEffect(() => {
    if (!showParticles) return;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let animationFrameId;

    const resizeCanvas = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    // Particle pool
    const particles = Array.from({ length: 45 }, () => ({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      radius: Math.random() * 2 + 0.8,
      alpha: Math.random() * 0.6 + 0.25,
      vx: (Math.random() - 0.5) * 0.4,
      vy: -Math.random() * 0.5 - 0.1,
      color: Math.random() > 0.4 ? '#06b6d4' : '#3b82f6'
    }));

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;

        if (p.y < 0) {
          p.y = canvas.height;
          p.x = Math.random() * canvas.width;
        }
        if (p.x < 0 || p.x > canvas.width) p.vx *= -1;

        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, Math.PI * 2);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = p.alpha;
        ctx.shadowBlur = 10;
        ctx.shadowColor = p.color;
        ctx.fill();
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', resizeCanvas);
      cancelAnimationFrame(animationFrameId);
    };
  }, [showParticles]);

  return (
    <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
      {/* Background base */}
      <div className={`absolute inset-0 ${dark ? 'bg-gradient-to-b from-[#050914] via-[#0c1427] to-[#050914]' : 'bg-[#f8fafc]'}`} />

      {/* Blueprint Grid Lines */}
      <div className={`absolute inset-0 bg-blueprint-grid ${dark ? 'opacity-20 invert' : 'opacity-70'}`} />

      {/* Radial Blue Light Orbs */}
      <div className={`absolute -top-40 left-1/2 -translate-x-1/2 w-[800px] h-[500px] ${dark ? 'bg-gradient-to-b from-blue-600/25 via-cyan-500/20 to-transparent' : 'bg-gradient-to-b from-blue-400/10 via-cyan-400/10 to-transparent'} blur-[140px] rounded-full`} />
      <div className={`absolute top-[40%] -right-40 w-[600px] h-[600px] ${dark ? 'bg-cyan-500/15' : 'bg-cyan-500/8'} blur-[150px] rounded-full pointer-events-none`} />
      <div className={`absolute top-[70%] -left-40 w-[600px] h-[600px] ${dark ? 'bg-blue-600/15' : 'bg-blue-500/8'} blur-[150px] rounded-full pointer-events-none`} />

      {/* Interactive Particles Canvas */}
      {showParticles && (
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full" />
      )}
    </div>
  );
};
