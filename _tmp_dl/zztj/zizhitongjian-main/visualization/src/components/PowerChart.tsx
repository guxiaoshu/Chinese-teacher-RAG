import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import type { PowerDistributionUnified } from '../types/unified';

interface PowerChartProps {
  data: PowerDistributionUnified[];
  onPowerClick?: (power: PowerDistributionUnified) => void;
}

export function PowerChart({ data, onPowerClick }: PowerChartProps) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || data.length === 0) return;

    const container = containerRef.current;
    const width = container.clientWidth;
    const height = 300;
    const margin = { top: 30, right: 30, bottom: 70, left: 60 };

    // Clear previous content
    d3.select(svgRef.current).selectAll('*').remove();

    const svg = d3
      .select(svgRef.current)
      .attr('width', width)
      .attr('height', height);

    // Take top 10 powers
    const topData = data.slice(0, 10);

    // Create scales
    const xScale = d3
      .scaleBand()
      .domain(topData.map((d) => d.power))
      .range([margin.left, width - margin.right])
      .padding(0.2);

    const yScale = d3
      .scaleLinear()
      .domain([0, d3.max(topData, (d) => d.count) || 0])
      .nice()
      .range([height - margin.bottom, margin.top]);

    // Color scale
    const colorScale = d3.scaleOrdinal(d3.schemeTableau10);

    // Draw axes
    svg
      .append('g')
      .attr('transform', `translate(0, ${height - margin.bottom})`)
      .call(d3.axisBottom(xScale))
      .selectAll('text')
      .attr('transform', 'rotate(-45)')
      .style('text-anchor', 'end')
      .style('font-size', '11px')
      .style('fill', '#2c1810');

    svg
      .append('g')
      .attr('transform', `translate(${margin.left}, 0)`)
      .call(d3.axisLeft(yScale))
      .selectAll('text')
      .style('fill', '#2c1810');

    // Draw bars
    svg
      .selectAll('.bar')
      .data(topData)
      .enter()
      .append('rect')
      .attr('class', 'bar')
      .attr('x', (d) => xScale(d.power) || 0)
      .attr('y', (d) => yScale(d.count))
      .attr('width', xScale.bandwidth())
      .attr('height', (d) => height - margin.bottom - yScale(d.count))
      .attr('fill', (_, i) => colorScale(i.toString()))
      .attr('rx', 4)
      .style('cursor', 'pointer')
      .on('click', (_, d) => onPowerClick?.(d))
      .on('mouseover', function () {
        d3.select(this).attr('opacity', 0.8);
      })
      .on('mouseout', function () {
        d3.select(this).attr('opacity', 1);
      });

    // Add value labels
    svg
      .selectAll('.label')
      .data(topData)
      .enter()
      .append('text')
      .attr('class', 'label')
      .attr('x', (d) => (xScale(d.power) || 0) + xScale.bandwidth() / 2)
      .attr('y', (d) => yScale(d.count) - 5)
      .attr('text-anchor', 'middle')
      .style('font-size', '11px')
      .style('fill', '#2c1810')
      .text((d) => d.count);

    // Add title
    svg
      .append('text')
      .attr('x', width / 2)
      .attr('y', 15)
      .attr('text-anchor', 'middle')
      .style('font-size', '14px')
      .style('font-weight', 'bold')
      .style('fill', '#2c1810')
      .text('各势力人物分布');

  }, [data, onPowerClick]);

  return (
    <div ref={containerRef} className="w-full bg-white rounded-lg shadow-md p-4">
      <svg ref={svgRef} className="w-full" />
    </div>
  );
}
