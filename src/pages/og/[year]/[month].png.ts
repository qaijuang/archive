import type { APIRoute } from "astro";
import fs from "node:fs/promises";
import path from "node:path";
import satori from "satori";
import { Resvg } from "@resvg/resvg-js";

// Types

interface Contribution {
  repo: string;
  repo_language: string;
}

interface Stats {
  total_prs: number;
  repos_touched: string[];
  languages: string[];
  total_lines_changed: number;
}

interface MonthData {
  month: string;
  contributions: Contribution[];
  stats: Stats;
}

// Static paths

export async function getStaticPaths() {
  const files = import.meta.glob("/data/contributions/*.json", {
    eager: true,
  }) as Record<string, MonthData>;

  return Object.entries(files).map(([filePath, data]) => {
    const slug = filePath.split("/").pop()!.replace(".json", "");
    const [year, month] = slug.split("-");
    return { params: { year, month }, props: { data } };
  });
}

// Design tokens

const T = {
  bg: "#111009",
  text: "#e0d9cd",
  muted: "#6b6358",
  amber: "#c9913a",
  border: "#2e2b24",
} as const;

// Helper

const MONTH_NAMES = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function buildLede(stats: Stats): { line1: string; line2: string | null } {
  const { total_prs, repos_touched, languages } = stats;

  const prStr = `${total_prs} contribution${total_prs !== 1 ? "s" : ""}`;
  const repoStr = `${repos_touched.length} repo${repos_touched.length !== 1 ? "s" : ""}`;

  const line1 = `${prStr} across ${repoStr}`;

  if (languages.length === 0) return { line1, line2: null };

  const joined =
    languages.length === 1
      ? languages[0]
      : languages.slice(0, -1).join(" · ") +
        " · " +
        languages[languages.length - 1];

  return { line1, line2: `in ${joined}` };
}

// Thin helper so the Satori tree stays readable without JSX
function el(
  type: string,
  style: Record<string, unknown>,
  children?: unknown,
  extraProps: Record<string, unknown> = {},
): Record<string, unknown> {
  return { type, props: { style, ...extraProps, children } };
}

// Card builder

function buildCard(
  monthName: string,
  year: string,
  data: MonthData,
): Record<string, unknown> {
  const isEmpty = data.contributions.length === 0;
  const accent = isEmpty ? T.border : T.amber;
  const statsColor = isEmpty ? T.muted : T.amber;

  const { line1, line2 } = isEmpty
    ? { line1: "No contributions this month.", line2: null }
    : buildLede(data.stats);

  // Repo names row, the top 4, joined with  ·
  const repoLine = data.stats.repos_touched.slice(0, 4).join("  ·  ");

  return el(
    "div",
    {
      display: "flex",
      width: "1200px",
      height: "630px",
      backgroundColor: T.bg,
      fontFamily: '"IBM Plex Mono"',
      position: "relative",
    },
    [
      // Left accent strip
      el("div", {
        position: "absolute",
        top: 0,
        left: 0,
        width: "4px",
        height: "630px",
        backgroundColor: accent,
      }),

      // Main content column
      el(
        "div",
        {
          display: "flex",
          flexDirection: "column",
          padding: "72px 80px",
          width: "100%",
          height: "100%",
        },
        [
          // Header row: wordmark ←→ arrow
          el(
            "div",
            {
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              marginBottom: "56px",
            },
            [
              el(
                "span",
                {
                  fontSize: "16px",
                  fontWeight: 400,
                  color: T.muted,
                  letterSpacing: "0.1em",
                },
                "archive",
              ),

              el(
                "svg",
                {
                  width: "28px",
                  height: "28px",
                  display: "block",
                },
                [
                  el(
                    "g",
                    {},
                    [
                      el("line", {}, undefined, {
                        x1: 8,
                        y1: 24,
                        x2: 22,
                        y2: 10,
                      }),
                      el("line", {}, undefined, {
                        x1: 22,
                        y1: 10,
                        x2: 22,
                        y2: 17,
                      }),
                      el("line", {}, undefined, {
                        x1: 22,
                        y1: 10,
                        x2: 15,
                        y2: 10,
                      }),
                    ],
                    {
                      stroke: accent,
                      strokeLinecap: "round",
                      strokeLinejoin: "round",
                      fill: "none",
                      strokeWidth: 2.5,
                    },
                  ),
                ],
                { viewBox: "0 0 32 32" },
              ),
            ],
          ),

          // Month + year hero
          el(
            "div",
            {
              fontSize: "76px",
              fontWeight: 500,
              color: T.text,
              letterSpacing: "-0.02em",
              lineHeight: 1.05,
              marginBottom: "28px",
            },
            `${monthName} ${year}`,
          ),

          // Thin rule
          el("div", {
            width: "100%",
            height: "1px",
            backgroundColor: T.border,
            marginBottom: "32px",
          }),

          // Stats / lede
          el(
            "div",
            {
              display: "flex",
              flexDirection: "column",
              gap: "8px",
            },
            [
              el(
                "span",
                {
                  fontSize: "22px",
                  fontWeight: 400,
                  color: statsColor,
                  lineHeight: 1.4,
                },
                line1,
              ),

              ...(line2
                ? [
                    el(
                      "span",
                      {
                        fontSize: "22px",
                        fontWeight: 400,
                        color: statsColor,
                        lineHeight: 1.4,
                      },
                      line2,
                    ),
                  ]
                : []),
            ],
          ),

          // Push repo names to bottom
          ...(repoLine
            ? [
                el("div", { flex: 1 }),
                el(
                  "div",
                  {
                    fontSize: "14px",
                    fontWeight: 400,
                    color: T.muted,
                    letterSpacing: "0.02em",
                    lineHeight: 1,
                  },
                  repoLine,
                ),
              ]
            : [el("div", { flex: 1 })]),
        ],
      ),
    ],
  );
}

// Route handler

export const GET: APIRoute = async ({ params, props }) => {
  const { year, month } = params as { year: string; month: string };
  const { data } = props as { data: MonthData };

  // Load fonts once per request (Astro caches module-level code at build)
  const fontsDir = path.resolve(
    "./node_modules/@fontsource/ibm-plex-mono/files",
  );

  const [fontRegular, fontMedium] = await Promise.all([
    fs.readFile(path.join(fontsDir, "ibm-plex-mono-latin-400-normal.woff")),
    fs.readFile(path.join(fontsDir, "ibm-plex-mono-latin-500-normal.woff")),
  ]);

  const monthName = MONTH_NAMES[parseInt(month, 10) - 1];
  const card = buildCard(monthName, year, data);

  const svg = await satori(card as any, {
    width: 1200,
    height: 630,
    fonts: [
      {
        name: "IBM Plex Mono",
        data: fontRegular,
        weight: 400,
        style: "normal",
      },
      {
        name: "IBM Plex Mono",
        data: fontMedium,
        weight: 500,
        style: "normal",
      },
    ],
  });

  const resvg = new Resvg(svg, {
    fitTo: { mode: "width", value: 1200 },
  });
  const png = resvg.render().asPng();

  return new Response(new Uint8Array(png), {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
};
