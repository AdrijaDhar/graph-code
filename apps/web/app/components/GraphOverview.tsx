"use client";
import { useEffect, useRef } from "react";

export interface OverviewNode {
  id: string;
  label: string;
  path?: string;
  name?: string;
  qualified_name?: string;
  size: number;
}

export interface OverviewEdge {
  source: string;
  target: string;
}

/** The "here's your whole codebase" moment — a file-level dependency map shown
 * automatically right after a repo loads, before the user has to know any symbol
 * name to type. Deliberately reuses DependencyGraph.tsx's proven D3 force-directed
 * pattern (drag, zoom, tooltips, halo text) rather than a heavier dedicated
 * large-graph library (Cosmograph was evaluated: its current version pulls in an
 * async DuckDB-WASM data-prep pipeline sized for tens-of-thousands-of-points
 * datasets, which is real, unnecessary weight and unverified click-interaction risk
 * for what is actually a module-level graph — realistically tens to a few hundred
 * nodes for any repo this tool would index, well within plain SVG D3's comfort
 * zone, and this exact rendering approach is already tested and working). */
export function GraphOverview({
  nodes,
  edges,
  onSelectNode,
  height = 560,
}: {
  nodes: OverviewNode[];
  edges: OverviewEdge[];
  onSelectNode?: (node: OverviewNode) => void;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const d3 = (window as any).d3;
    if (!d3 || !svgRef.current || !containerRef.current || nodes.length === 0) return;

    const width = containerRef.current.clientWidth || 600;
    const graphNodes = nodes.map((n) => ({ ...n })) as any[];
    const byId = new Set(graphNodes.map((n) => n.id));
    const links = edges.filter((e) => byId.has(e.source) && byId.has(e.target)).map((e) => ({ ...e }));

    const maxSize = Math.max(1, ...graphNodes.map((n) => n.size || 0));
    const radius = (d: any) => 6 + 14 * Math.sqrt((d.size || 0) / maxSize);

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const defs = svg.append("defs");
    const gridId = "gc-overview-grid";
    const pattern = defs
      .append("pattern")
      .attr("id", gridId)
      .attr("width", 22)
      .attr("height", 22)
      .attr("patternUnits", "userSpaceOnUse");
    pattern.append("circle").attr("cx", 1.5).attr("cy", 1.5).attr("r", 1).attr("fill", "rgba(255,255,255,0.06)");
    svg.append("rect").attr("width", "100%").attr("height", "100%").attr("fill", `url(#${gridId})`);

    defs
      .append("marker")
      .attr("id", "overview-arrow")
      .attr("viewBox", "0 -4 8 8")
      .attr("refX", 16)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", "#4ecfcf")
      .attr("opacity", 0.7);

    const grad = defs.append("radialGradient").attr("id", "overview-node-fill").attr("cx", "35%").attr("cy", "30%");
    grad.append("stop").attr("offset", "0%").attr("stop-color", "#8b98b8").attr("stop-opacity", 1);
    grad.append("stop").attr("offset", "100%").attr("stop-color", "#8b98b8").attr("stop-opacity", 0.7);

    const g = svg.append("g");
    svg.call(
      d3
        .zoom()
        .scaleExtent([0.2, 4])
        .on("zoom", (event: any) => g.attr("transform", event.transform))
    );

    const simulation = d3
      .forceSimulation(graphNodes)
      .force(
        "link",
        d3.forceLink(links).id((d: any) => d.id).distance(110)
      )
      .force("charge", d3.forceManyBody().strength(-260))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide((d: any) => radius(d) + 18));

    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", "#4ecfcf")
      .attr("stroke-width", 1.2)
      .attr("stroke-dasharray", "4,3")
      .attr("marker-end", "url(#overview-arrow)")
      .attr("opacity", 0.4);

    const tooltip = d3
      .select(containerRef.current)
      .append("div")
      .attr(
        "class",
        "pointer-events-none absolute z-10 rounded-lg bg-[#151d33] border border-white/10 shadow-xl px-3 py-2 text-xs text-[#e8eefc] opacity-0 transition-opacity max-w-xs"
      );

    const node = g
      .append("g")
      .selectAll("circle.node")
      .data(graphNodes)
      .join("circle")
      .attr("class", "node")
      .attr("r", radius)
      .attr("fill", "url(#overview-node-fill)")
      .attr("stroke", "rgba(255,255,255,0.15)")
      .attr("stroke-width", 1)
      .style("cursor", "pointer")
      .style("filter", "drop-shadow(0 2px 4px rgba(0,0,0,0.4))")
      .on("mouseenter", (_event: any, d: any) => {
        tooltip
          .style("opacity", 1)
          .html(
            `<div class="font-semibold text-white">${d.path || d.qualified_name || d.id}</div>` +
              `<div class="text-[#e8eefc]/50 mt-0.5">${d.size} function${d.size === 1 ? "" : "s"}/class${d.size === 1 ? "" : "es"}</div>` +
              `<div class="text-[#e8eefc]/35 mt-1">click to explore</div>`
          );
      })
      .on("mousemove", (event: any) => {
        const [x, y] = d3.pointer(event, containerRef.current);
        tooltip.style("left", `${x + 14}px`).style("top", `${y + 14}px`);
      })
      .on("mouseleave", () => tooltip.style("opacity", 0))
      .on("click", (_event: any, d: any) => onSelectNode && onSelectNode(d))
      .call(
        d3
          .drag()
          .on("start", (event: any, d: any) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event: any, d: any) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event: any, d: any) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    const label = g
      .append("g")
      .selectAll("text")
      .data(graphNodes)
      .join("text")
      .text((d: any) => (d.path || d.qualified_name || d.id).split("/").pop())
      .attr("font-size", 10.5)
      .attr("font-family", "Inter, ui-sans-serif, system-ui")
      .attr("fill", "#e8eefc")
      .attr("dx", (d: any) => radius(d) + 4)
      .attr("dy", 4)
      .attr("paint-order", "stroke")
      .attr("stroke", "#0a0f1e")
      .attr("stroke-width", 3)
      .style("pointer-events", "none");

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
    });

    return () => {
      simulation.stop();
      tooltip.remove();
    };
  }, [nodes, edges, height, onSelectNode]);

  return (
    <div ref={containerRef} className="relative w-full border border-white/[0.06] rounded-xl bg-[#0a0f1e] overflow-hidden">
      <svg ref={svgRef} className="w-full block" style={{ height }} />
      <div className="absolute bottom-3 right-3 text-[10px] text-[#e8eefc]/45 bg-[#0a0f1e]/70 backdrop-blur px-2.5 py-1.5 rounded-lg border border-white/5">
        node size = functions/classes in that file · dashed = imports
      </div>
      <div className="absolute top-3 right-3 text-[10px] text-[#e8eefc]/35 bg-[#0a0f1e]/70 backdrop-blur px-2.5 py-1.5 rounded-lg border border-white/5">
        drag · scroll to zoom · click a file to explore
      </div>
    </div>
  );
}
