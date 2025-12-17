export function generateStatsGraph(rankings, stage1) {
  const width = 1400;
  const height = 520;
  const padding = 100;
  const gap = 120;
  const rightMargin = 180;
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d');

  // Background
  ctx.fillStyle = 'white';
  ctx.fillRect(0, 0, width, height);

  // Identify timed-out models from stage1 (elapsed_time is null and response indicates failure)
  const timedOutModels = [];
  if (stage1) {
    for (const s of stage1) {
      if (s.elapsed_time === null || s.elapsed_time === undefined) {
        const response = s.response || '';
        if (response.includes('No response') || response.toLowerCase().includes('did not reply')) {
          const shortName = (s.model.split('/')[1] || s.model).substring(0, 20);
          timedOutModels.push(shortName);
        }
      }
    }
  }

  const missingCostModels = [];

  // Data prep
  const data = rankings.map(r => {
    // Use total_elapsed_time/total_cost from aggregate rankings
    // These include all stages combined
    let delay = r.total_elapsed_time ?? null;
    let cost = r.total_cost ?? null;

    // Fall back to stage1 data if aggregate totals not available
    if (stage1 && (delay === null || cost === null)) {
        const s1 = stage1.find(s => s.model === r.model);
        if (s1) {
            if (delay === null && s1.elapsed_time !== null && s1.elapsed_time !== undefined) delay = s1.elapsed_time;
            if (cost === null && s1.cost !== null && s1.cost !== undefined) cost = s1.cost;
        }
    }

    const shortName = (r.model.split('/')[1] || r.model).substring(0, 20);
    if (cost === null || cost === undefined) {
      missingCostModels.push(shortName);
    }

    return {
      name: shortName,
      rank: r.average_rank,
      delay: delay,
      cost: cost
    };
  });

  const plotWidth = (width - (padding * 2) - gap - rightMargin) / 2;

  // Helper to draw a plot
  const drawPlot = (offsetX, title, yKey, yLabel, formatY) => {
    const plotHeight = height - (padding * 2);
    const startX = offsetX + padding;
    const startY = height - padding;

    // Find ranges
    const xMin = Math.min(...data.map(d => d.rank));
    const xMax = Math.max(...data.map(d => d.rank));
    
    // Log scale Y setup
    const yValues = data
      .map(d => d[yKey])
      .filter(v => typeof v === 'number' && Number.isFinite(v) && v > 0);
    let yMinVal = yValues.length > 0 ? Math.min(...yValues) : 0.001;
    let yMaxVal = yValues.length > 0 ? Math.max(...yValues) : 0.01;
    
    if (yMaxVal <= 0) yMaxVal = 0.01;
    if (yMinVal >= yMaxVal) yMinVal = yMaxVal / 10;

    // Add some padding to log range
    const yMin = yMinVal * 0.9;
    const yMax = yMaxVal * 1.1;
    
    const logMin = Math.log10(yMin);
    const logMax = Math.log10(yMax);

    const xDomainMin = xMin - 0.5;
    const xDomainMax = xMax + 0.5;

    const xScale = (val) => startX + ((val - xDomainMin) / (xDomainMax - xDomainMin)) * plotWidth;
    
    const yScale = (val) => {
        if (val <= 0) return startY; // Clamp 0 to bottom
        const logVal = Math.log10(val);
        const ratio = (logVal - logMin) / (logMax - logMin);
        return startY - (ratio * plotHeight);
    };

    // Draw axes
    ctx.beginPath();
    ctx.strokeStyle = '#333';
    ctx.lineWidth = 1;
    ctx.moveTo(startX, startY);
    ctx.lineTo(startX + plotWidth, startY); // X axis
    ctx.moveTo(startX, startY);
    ctx.lineTo(startX, startY - plotHeight); // Y axis
    ctx.stroke();

    // Title
    ctx.fillStyle = '#333';
    ctx.font = 'bold 18px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(title, startX + plotWidth / 2, padding / 2);

    // Show timed-out models note (only on the delay plot, which is the first one)
    if (yKey === 'delay' && timedOutModels.length > 0) {
      ctx.fillStyle = 'red';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      const timeoutText = 'Timed out: ' + timedOutModels.join(', ');
      // Wrap text if too wide
      const maxWidth = plotWidth;
      const words = timeoutText.split(' ');
      let lines = [];
      let currentLine = '';
      for (const word of words) {
        const testLine = currentLine ? currentLine + ' ' + word : word;
        const metrics = ctx.measureText(testLine);
        if (metrics.width > maxWidth && currentLine) {
          lines.push(currentLine);
          currentLine = word;
        } else {
          currentLine = testLine;
        }
      }
      if (currentLine) lines.push(currentLine);
      // Draw wrapped lines below title
      let yOffset = padding / 2 + 14;
      for (const line of lines) {
        ctx.fillText(line, startX + plotWidth / 2, yOffset);
        yOffset += 12;
      }
    }

    // Show missing-cost models note (only on the cost plot)
    if (yKey === 'cost' && missingCostModels.length > 0) {
      ctx.fillStyle = 'red';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'center';
      const missingText = 'No cost returned: ' + missingCostModels.join(', ');
      const maxWidth = plotWidth;
      const words = missingText.split(' ');
      let lines = [];
      let currentLine = '';
      for (const word of words) {
        const testLine = currentLine ? currentLine + ' ' + word : word;
        const metrics = ctx.measureText(testLine);
        if (metrics.width > maxWidth && currentLine) {
          lines.push(currentLine);
          currentLine = word;
        } else {
          currentLine = testLine;
        }
      }
      if (currentLine) lines.push(currentLine);

      let yOffset = padding / 2 + 14;
      for (const line of lines) {
        ctx.fillText(line, startX + plotWidth / 2, yOffset);
        yOffset += 12;
      }
    }

    // Labels
    ctx.font = '16px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('Rank (lower is better)', startX + plotWidth / 2, height - 20);
    
    ctx.save();
    ctx.translate(startX - 70, startY - plotHeight / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.fillText(yLabel + ' (Log Scale)', 0, 0);
    ctx.restore();

    // Grid lines (horizontal) & Y-axis labels
    ctx.strokeStyle = '#eee';
    ctx.lineWidth = 1;
    ctx.fillStyle = '#666';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'middle';
    ctx.font = '14px sans-serif';

    for (let i = 0; i <= 5; i++) {
        const ratio = i / 5;
        const logVal = logMin + ratio * (logMax - logMin);
        const val = Math.pow(10, logVal);
        const yPos = startY - (ratio * plotHeight);
        
        // Grid line
        if (i > 0) {
            ctx.beginPath();
            ctx.moveTo(startX, yPos);
            ctx.lineTo(startX + plotWidth, yPos);
            ctx.stroke();
        }

        // Label
        ctx.fillText(formatY(val), startX - 5, yPos);
    }

    // X-axis labels
    ctx.textAlign = 'center';
    ctx.textBaseline = 'top';
    const startRank = Math.ceil(xMin);
    const endRank = Math.floor(xMax);
    
    for (let r = startRank; r <= endRank; r++) {
        const xPos = xScale(r);
        // Only draw if within plot width (should be, given domain)
        if (xPos >= startX && xPos <= startX + plotWidth) {
             ctx.fillText(r.toString(), xPos, startY + 5);
        }
    }

    // Points - track label positions to avoid overlap
    const labelPositions = [];
    data.forEach((d, idx) => {
      const x = xScale(d.rank);
      const val = d[yKey];

      if (val === null || val === undefined) {
        return;
      }
      
      // For zero values, plot at the bottom of the chart with a different marker
      const isZero = val <= 0;
      const y = isZero ? startY : yScale(val);

      ctx.beginPath();
      // Use a different color for zero values to indicate they're at $0
      ctx.fillStyle = isZero ? '#888' : '#2d8a2d';
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
      
      // Add a small indicator line for zero values
      if (isZero) {
        ctx.strokeStyle = '#888';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x - 3, y);
        ctx.lineTo(x + 3, y);
        ctx.stroke();
      }

      // Calculate label position with collision avoidance
      const labelText = d.name;
      ctx.font = '14px sans-serif';
      const textWidth = ctx.measureText(labelText).width;
      const labelHeight = 18;
      
      let labelX = x + 8;
      let labelY = y + 5;
      let placeAbove = false;
      
      // Check for collisions with existing labels
      for (const pos of labelPositions) {
        const xOverlap = labelX < pos.x + pos.width && labelX + textWidth > pos.x;
        const yOverlap = Math.abs(pos.y - labelY) < labelHeight;
        if (xOverlap && yOverlap) {
          placeAbove = true;
          break;
        }
      }
      
      if (placeAbove) {
        labelY = y - 10 - (idx % 3) * labelHeight; // Stagger vertically
      }
      
      labelPositions.push({ x: labelX, y: labelY, width: textWidth });

      ctx.fillStyle = '#444';
      ctx.font = '14px sans-serif';
      ctx.textAlign = 'left';
      ctx.fillText(labelText, labelX, labelY);
    });
  };

  drawPlot(0, 'Delay vs Rank', 'delay', 'Seconds', v => Number(v.toPrecision(2)).toString());
  drawPlot(plotWidth + gap + padding, 'Cost vs Rank', 'cost', 'USD', v => '$' + Number(v.toPrecision(2)).toString());

  return canvas.toDataURL('image/png');
}
