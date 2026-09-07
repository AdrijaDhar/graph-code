"use client";
import { useEffect, useRef } from "react";

export interface GraphNode {
  id: string;
  label: string;
  qualified_name?: string;
  path?: string;
  via?: string;
  hop?: number;
  from?: string;
  start_line?: number;
  end_line?: number;
}

const NODE_COLOR: Record<string, string> = {
  Function: "#4f8cff",
  Class: "#d17bff",
  Module: "#8b98b8",
  Variable: "#4ecf95",
};

const EDGE_COLOR: Record<string, string> = {
  CALLS: "#4f8cff",
  IMPORTS: "#4ecfcf",
  INHERITS: "#d17bff",
  CONTAINS: "#5a6a8c",
};

/** Force-directed rendering of a blast_radius() result via D3 (loaded globally by a
 * <Script> tag in layout.tsx — no npm dependency). D3 owns the SVG's internals
 * imperatively (positions via forceSimulation, drag, zoom) while React only ever
 * renders the two container elements once; this avoids React and D3 fighting over
 * the same DOM nodes, the standard way to mix the two. */
export function DependencyGraph({
  origin,
  nodes,
  onSelectNode,
  height = 440,
}: {
  origin: GraphNode;
  nodes: GraphNode[];
  onSelectNode?: (node: GraphNode) => void;
  height?: number;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const d3 = (window as any).d3;
    if (!d3 || !svgRef.current || !containerRef.current) return;

    const width = containerRef.current.clientWidth || 600;
    const byId = new Map<string, GraphNode>();
    byId.set(origin.id, origin);
    for (const n of nodes) if (!byId.has(n.id)) byId.set(n.id, n);
    const graphNodes = Array.from(byId.values()).map((n) => ({ ...n })) as any[];
    const links = nodes
      .filter((n) => n.from && byId.has(n.from))
      .map((n) => ({ source: n.from as string, target: n.id, type: n.via || "CONTAINS" }));

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();
    svg.attr("viewBox", `0 0 ${width} ${height}`);

    const defs = svg.append("defs");

    // subtle dot-grid background — reads as "tool", not a bare black rectangle
    const gridId = "gc-grid";
    const pattern = defs
      .append("pattern")
      .attr("id", gridId)
      .attr("width", 22)
      .attr("height", 22)
      .attr("patternUnits", "userSpaceOnUse");
    pattern.append("circle").attr("cx", 1.5).attr("cy", 1.5).attr("r", 1).attr("fill", "rgba(255,255,255,0.06)");
    svg.append("rect").attr("width", "100%").attr("height", "100%").attr("fill", `url(#${gridId})`);

    // directional arrowheads, one per edge type so color matches the line
    for (const [type, color] of Object.entries(EDGE_COLOR)) {
      defs
        .append("marker")
        .attr("id", `arrow-${type}`)
        .attr("viewBox", "0 -4 8 8")
        .attr("refX", 16)
        .attr("refY", 0)
        .attr("markerWidth", 6)
        .attr("markerHeight", 6)
        .attr("orient", "auto")
        .append("path")
        .attr("d", "M0,-4L8,0L0,4")
        .attr("fill", color)
        .attr("opacity", 0.8);
    }

    // radial gradients per node type — flat fills read flat; a soft highlight reads "designed"
    for (const [labelType, color] of Object.entries(NODE_COLOR)) {
      const grad = defs
        .append("radialGradient")
        .attr("id", `node-fill-${labelType}`)
        .attr("cx", "35%")
        .attr("cy", "30%");
      grad.append("stop").attr("offset", "0%").attr("stop-color", color).attr("stop-opacity", 1);
      grad.append("stop").attr("offset", "100%").attr("stop-color", color).attr("stop-opacity", 0.75);
    }

    const g = svg.append("g");

    svg.call(
      d3
        .zoom()
        .scaleExtent([0.3, 3])
        .on("zoom", (event: any) => g.attr("transform", event.transform))
    );

    const simulation = d3
      .forceSimulation(graphNodes)
      .force(
        "link",
        d3.forceLink(links).id((d: any) => d.id).distance(95)
      )
      .force("charge", d3.forceManyBody().strength(-240))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force("collide", d3.forceCollide(36));

    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", (d: any) => EDGE_COLOR[d.type] || "#5a6a8c")
      .attr("stroke-width", (d: any) => (d.type === "INHERITS" ? 2 : 1.4))
      .attr("stroke-dasharray", (d: any) => (d.type === "IMPORTS" ? "4,3" : d.type === "CONTAINS" ? "1,3" : null))
      .attr("marker-end", (d: any) => `url(#arrow-${d.type})`)
      .attr("opacity", 0.55);

    const tooltip = d3
      .select(containerRef.current)
      .append("div")
      .attr(
        "class",
        "pointer-events-none absolute z-10 rounded-lg bg-[#151d33] border border-white/10 shadow-xl px-3 py-2 text-xs text-[#e8eefc] opacity-0 transition-opacity max-w-xs"
      );

    // soft pulsing halo behind the origin node so it reads as "you are here"
    g.append("circle")
      .attr("class", "origin-pulse")
      .attr("r", 18)
      .attr("fill", "none")
      .attr("stroke", NODE_COLOR[origin.label] || "#4f8cff")
      .attr("stroke-width", 1.5)
      .attr("opacity", 0.5);

    const node = g
      .append("g")
      .selectAll("circle.node")
      .data(graphNodes)
      .join("circle")
      .attr("class", "node")
      .attr("r", (d: any) => (d.id === origin.id ? 13 : 8))
      .attr("fill", (d: any) => `url(#node-fill-${d.label})`)
      .attr("stroke", (d: any) => (d.id === origin.id ? "#fff" : "rgba(255,255,255,0.15)"))
      .attr("stroke-width", (d: any) => (d.id === origin.id ? 2 : 1))
      .style("cursor", "pointer")
      .style("filter", "drop-shadow(0 2px 4px rgba(0,0,0,0.4))")
      .on("mouseenter", (_event: any, d: any) => {
        tooltip
          .style("opacity", 1)
          .html(
            `<div class="font-semibold text-white">${d.qualified_name || d.path || d.id}</div>` +
              `<div class="text-[#e8eefc]/50 mt-0.5">${d.label}${d.path ? " · " + d.path : ""}</div>` +
              (d.id !== origin.id ? `<div class="text-[#e8eefc]/35 mt-1">click to view source</div>` : "")
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
      .text((d: any) => d.qualified_name?.split(".").pop() || d.path?.split("/").pop() || d.id)
      .attr("font-size", 10.5)
      .attr("font-family", "Inter, ui-sans-serif, system-ui")
      .attr("fill", "#e8eefc")
      .attr("dx", 14)
      .attr("dy", 4)
      // halo behind the text so it stays legible over edges/grid without a separate
      // background rect (cheaper than measuring text width for a pill)
      .attr("paint-order", "stroke")
      .attr("stroke", "#0a0f1e")
      .attr("stroke-width", 3)
      .style("pointer-events", "none");

    const originNode = graphNodes.find((n) => n.id === origin.id);
    const pulse = g.select("circle.origin-pulse");

    simulation.on("tick", () => {
      link
        .attr("x1", (d: any) => d.source.x)
        .attr("y1", (d: any) => d.source.y)
        .attr("x2", (d: any) => d.target.x)
        .attr("y2", (d: any) => d.target.y);
      node.attr("cx", (d: any) => d.x).attr("cy", (d: any) => d.y);
      label.attr("x", (d: any) => d.x).attr("y", (d: any) => d.y);
      if (originNode) pulse.attr("cx", originNode.x).attr("cy", originNode.y);
    });

    return () => {
      simulation.stop();
      tooltip.remove();
    };
  }, [origin, nodes, height, onSelectNode]);

  return (
    <div ref={containerRef} className="relative w-full border border-white/[0.06] rounded-xl bg-[#0a0f1e] overflow-hidden">
      <svg ref={svgRef} className="w-full block" style={{ height }} />
      <div className="absolute bottom-3 right-3 flex gap-3 text-[10px] text-[#e8eefc]/45 bg-[#0a0f1e]/70 backdrop-blur px-2.5 py-1.5 rounded-lg border border-white/5">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full" style={{ background: NODE_COLOR.Function }} />
          Function
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full" style={{ background: NODE_COLOR.Class }} />
          Class
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full" style={{ background: NODE_COLOR.Module }} />
          Module
        </span>
      </div>
      <div className="absolute top-3 right-3 text-[10px] text-[#e8eefc]/35 bg-[#0a0f1e]/70 backdrop-blur px-2.5 py-1.5 rounded-lg border border-white/5">
        drag · scroll to zoom
      </div>
    </div>
  );
}
