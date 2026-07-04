const { Canvas } = require('skia-canvas');
const GIFEncoder = require('gif-encoder-2');
const fs = require('fs');
const path = require('path');

// Colors config
const COLORS = {
  blue: {
    dark: '#1a3a8a',
    light: '#1e3d99',
    label: 'x2',
    labelColor: '#5B8CFF'
  },
  green: {
    dark: '#0d4d20',
    light: '#0f5c26',
    label: 'x3',
    labelColor: '#22c55e'
  },
  yellow: {
    dark: '#5a3f00',
    light: '#6b4c00',
    label: 'x5',
    labelColor: '#eab308'
  },
  red: {
    dark: '#7a1010',
    light: '#8a1515',
    label: 'x10',
    labelColor: '#ef4444'
  }
};

// Perfectly interleaved list of 30 colors (12 blue, 10 green, 6 yellow, 2 red)
const WHEEL_LAYOUT = [
  'blue', 'green', 'blue', 'green', 'yellow', 'green', 'yellow', 'blue', 'yellow', 'blue',
  'yellow', 'blue', 'green', 'blue', 'green', 'yellow', 'blue', 'green', 'blue', 'green',
  'blue', 'green', 'blue', 'red', 'blue', 'yellow', 'green', 'blue', 'green', 'red'
];

/**
 * Generates an animated spin GIF ending at the specified winIndex.
 * @param {number} winIndex The target slot index to stop at (0-29).
 * @param {string} outputPath Path to save the final GIF.
 */
async function generateSpinGif(winIndex, outputPath) {
  const width = 300;
  const height = 300;
  const canvas = new Canvas(width, height);
  const ctx = canvas.getContext('2d');
  
  const encoder = new GIFEncoder(width, height);
  encoder.start();
  encoder.setRepeat(0); // Loop forever
  encoder.setDelay(50); // 50ms per frame (20fps)
  encoder.setQuality(10); // Standard quality
  
  const totalFrames = 30;
  const radius = 120;
  const cx = width / 2;
  const cy = height / 2;
  
  // Calculate total rotation angle to land winIndex at 12 o'clock (-90 degrees)
  // Each slot spans 12 degrees. Slot i has center angle = -90 + i * 12 + 6.
  // When rotated by R, slot i center becomes -90 + i * 12 + 6 + R.
  // We want this center to align with -90:
  // -90 + winIndex * 12 + 6 + R = -90 (mod 360) => R = -(winIndex * 12 + 6) (mod 360).
  // To ensure at least 2 full spins (720 degrees):
  const targetOffset = (360 - (winIndex * 12 + 6) % 360) % 360;
  const totalAngle = 720 + targetOffset;
  
  for (let f = 0; f < totalFrames; f++) {
    // Easing out cubic: progress goes 0 to 1
    const progress = f / (totalFrames - 1);
    const easedProgress = 1 - Math.pow(1 - progress, 3);
    const currentRotation = totalAngle * easedProgress; // in degrees
    
    // Clear canvas with background color #1e1e2e
    ctx.fillStyle = '#1e1e2e';
    ctx.fillRect(0, 0, width, height);
    
    // 1. Draw the wheel slices
    for (let i = 0; i < 30; i++) {
      const colorName = WHEEL_LAYOUT[i];
      const colorCfg = COLORS[colorName];
      const fill = (i % 2 === 0) ? colorCfg.dark : colorCfg.light;
      
      // Start/End angles in degrees, shifted by -90 to align slot 0 at 12 o'clock on unrotated wheel
      const startDeg = -90 + i * 12 + currentRotation;
      const endDeg = -90 + (i + 1) * 12 + currentRotation;
      
      const startRad = startDeg * Math.PI / 180;
      const endRad = endDeg * Math.PI / 180;
      
      // Draw slice
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, startRad, endRad);
      ctx.closePath();
      ctx.fillStyle = fill;
      ctx.fill();
      
      // Draw boundary line
      ctx.lineWidth = 1.5;
      ctx.strokeStyle = '#1e1e2e';
      ctx.stroke();
      
      // 2. Draw multiplier text radially (at 70% of radius)
      const centerDeg = startDeg + 6;
      const centerRad = centerDeg * Math.PI / 180;
      
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(centerRad);
      ctx.fillStyle = colorCfg.labelColor;
      ctx.font = 'bold 11px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(colorCfg.label, radius * 0.7, 0);
      ctx.restore();
    }
    
    // 3. Draw outer border of the wheel
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#2a2a45';
    ctx.stroke();
    
    // 4. Draw central hub
    ctx.beginPath();
    ctx.arc(cx, cy, 25, 0, 2 * Math.PI);
    ctx.fillStyle = '#141422';
    ctx.fill();
    ctx.lineWidth = 3;
    ctx.strokeStyle = '#2a2a45';
    ctx.stroke();
    
    // 5. Draw central hub dot
    ctx.beginPath();
    ctx.arc(cx, cy, 4, 0, 2 * Math.PI);
    ctx.fillStyle = '#c8a84b';
    ctx.fill();
    
    // 6. Draw the top pointer arrow (pointing down at 12 o'clock, touching the wheel)
    // Wheel top is at cy - radius = 150 - 120 = 30.
    ctx.beginPath();
    ctx.moveTo(cx, 32);      // Tip pointing down
    ctx.lineTo(cx - 8, 18);  // Top-left
    ctx.lineTo(cx + 8, 18);  // Top-right
    ctx.closePath();
    ctx.fillStyle = '#c8a84b';
    ctx.fill();
    
    encoder.addFrame(ctx);
  }
  
  encoder.finish();
  const buffer = encoder.out.getData();
  fs.writeFileSync(outputPath, buffer);
}

// Command line interface
const args = process.argv.slice(2);
if (args.length < 2) {
  console.error("Usage: node wheel_spinner.js <winIndex> <outputPath>");
  process.exit(1);
}

const winIndex = parseInt(args[0], 10);
const outputPath = args[1];

if (isNaN(winIndex) || winIndex < 0 || winIndex >= 30) {
  console.error("Invalid winIndex. Must be 0-29.");
  process.exit(1);
}

generateSpinGif(winIndex, outputPath)
  .then(() => {
    process.exit(0);
  })
  .catch(err => {
    console.error(err);
    process.exit(1);
  });
