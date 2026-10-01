from html import escape
from shapely import wkt
from shapely.ops import nearest_points
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Flowable,
)
from pypdf import PdfReader
from iris.config import DISCLAIMER, ASSUMPTIONS


class MapDiagram(Flowable):
    width = 475
    height = 225

    def __init__(self, sources):
        super().__init__()
        self.width = 475
        self.height = 225
        self.sources = sources

    def draw(self):
        c = self.canv
        shapes = [
            (s["dataset"], s["payload"]["source_id"], wkt.loads(s["payload"]["geom"]))
            for s in self.sources
        ]
        minx = min(g.bounds[0] for _, _, g in shapes)
        miny = min(g.bounds[1] for _, _, g in shapes)
        maxx = max(g.bounds[2] for _, _, g in shapes)
        maxy = max(g.bounds[3] for _, _, g in shapes)
        scale = min(390 / max(maxx - minx, 1), 130 / max(maxy - miny, 1))

        def xy(x, y):
            return (
                30 + (390 - (maxx - minx) * scale) / 2 + (x - minx) * scale,
                60 + (140 - (maxy - miny) * scale) / 2 + (y - miny) * scale,
            )

        palette = {
            "parcels": colors.HexColor("#167c80"),
            "peat": colors.HexColor("#c18b32"),
            "substations": colors.HexColor("#ac354e"),
        }
        c.setFillColor(colors.HexColor("#f3f6f8"))
        c.rect(0, 0, self.width, self.height, fill=1, stroke=0)
        for dataset, id, g in sorted(shapes, key=lambda s: s[0] != "peat"):
            c.setStrokeColor(palette[dataset])
            c.setFillColor(palette[dataset])
            c.setLineWidth(2)
            if g.geom_type == "Point":
                x, y = xy(g.x, g.y)
                c.circle(x, y, 4, fill=1)
                c.setFont("Helvetica", 8)
                c.drawRightString(x + 10, y + 12, id)
            else:
                for poly in g.geoms if g.geom_type == "MultiPolygon" else [g]:
                    p = c.beginPath()
                    for ring in [poly.exterior, *poly.interiors]:
                        points = list(ring.coords)
                        p.moveTo(*xy(*points[0]))
                        for point in points[1:]:
                            p.lineTo(*xy(*point))
                        p.close()
                    c.drawPath(p, stroke=1, fill=0)
                if dataset == "parcels":
                    x, y = xy(g.centroid.x, g.centroid.y)
                    c.setFont("Helvetica", 8)
                    c.drawString(x - 20, y + 5, id)
        parcel = next(g for dataset, _, g in shapes if dataset == "parcels")
        grids = [g for dataset, _, g in shapes if dataset == "substations"]
        if grids:
            a, b = nearest_points(parcel, grids[0])
            ax, ay = xy(a.x, a.y)
            bx, by = xy(b.x, b.y)
            c.setStrokeColor(colors.HexColor("#526470"))
            c.setDash(3, 3)
            c.line(ax, ay, bx, by)
            c.setDash()
            c.setFillColor(colors.HexColor("#243746"))
            c.setFont("Helvetica", 8)
            c.drawCentredString(
                (ax + bx) / 2,
                (ay + by) / 2 + 10,
                f"{a.distance(b):,.2f} m shortest distance",
            )
        c.setFillColor(colors.HexColor("#243746"))
        c.setFont("Helvetica", 8)
        c.drawString(15, 210, "EPSG:25832 | schematic in grid metres | north up")
        c.drawString(435, 180, "N")
        c.line(438, 160, 438, 177)
        for i, (key, label) in enumerate(
            [
                ("parcels", "Parcel"),
                ("peat", "Peat coverage"),
                ("substations", "Substation"),
            ]
        ):
            c.setFillColor(palette[key])
            c.rect(15 + i * 150, 32, 9, 9, fill=1, stroke=0)
            c.setFillColor(colors.HexColor("#243746"))
            c.drawString(29 + i * 150, 33, label)
        c.drawString(
            15,
            15,
            "Synthetic geometry; overlapping peat outlines are unioned for calculations.",
        )


def make_report(path, kind, row, sources, run_id):
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="SmallText", fontName="Helvetica", fontSize=9, leading=13, spaceAfter=7
        )
    )
    styles["BodyText"].leading = 14

    def p(text, style="SmallText"):
        return Paragraph(escape(str(text)), styles[style])

    def table(items):
        t = Table([[p(a), p(b)] for a, b in items], colWidths=[190, 285], hAlign="LEFT")
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f5f5")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                ]
            )
        )
        return t

    title = "BESS" if kind == "bess" else "Peatland"
    story = [
        p(f"{title} prospecting report", "Title"),
        p(f"{row['country_code']} / {row['parcel_id']}", "Heading2"),
        p("SYNTHETIC DEMONSTRATION DATA - no real site or ownership claim", "Heading3"),
    ]
    values = [
        ("Parcel area", f"{row['area_m2']:,.2f} m2 / {row['area_ha']:.4f} ha"),
        ("Parcel source date", row["parcel_date"] or "Unknown (explicit flag)"),
    ]
    if kind == "bess":
        values += [
            (
                "Selected substation",
                f"{row['substation_id']} / {row['voltage_kv']:g} kV",
            ),
            ("Shortest distance", f"{row['distance_m']:,.2f} m"),
            ("Qualifying rule", "Area >= 2 ha; voltage >= 110 kV; distance <= 1,000 m"),
        ]
    else:
        values += [
            (
                "Deduplicated peat overlap",
                f"{row['overlap_m2']:,.2f} m2 ({row['overlap_percent']:.2f}%)",
            ),
            ("Indicative eco-points", f"{row['eco_points']:,.0f}"),
            (
                "Qualifying rule",
                "Parcel >= 3 ha; positive peat overlap; 8 eco-points/m2 of overlap",
            ),
        ]
    story += [
        table(values),
        Spacer(1, 14),
        MapDiagram(sources),
        p("Why this candidate qualifies", "Heading2"),
        p(
            "All inclusive screening thresholds shown above are satisfied. Candidate selection is ordered by country and parcel identifier. "
            + (
                "The nearest eligible substation is selected; ties use source identifier."
                if kind == "bess"
                else "Peat coverage is unioned before intersection with the parcel; repeated coverage adds no area."
            )
        ),
        PageBreak(),
        p("Calculations and source evidence", "Title"),
        p(f"Rule: {row['rule_version']} | Run: {run_id}"),
    ]
    calculations = (
        f"Area: {row['area_m2']:g} m2 / 10,000 = {row['area_ha']:g} ha. Distance: ST_Distance(parcel, substation) = {row['distance_m']:g} m."
        if kind == "bess"
        else f"Union peat, intersect parcel, measure: {row['overlap_m2']:g} m2. Overlap / parcel x 100 = {row['overlap_percent']:.6f}%. Eco-points: {row['overlap_m2']:g} x 8 = {row['eco_points']:g}."
    )
    story += [p(calculations), p("Source references", "Heading2")]
    for source in sources:
        r = source["payload"]
        story.append(
            p(
                f"{r['country_code']} / {source['dataset']} / {r['source_id']} | {source['source_file']} record {source['ordinal']} | source date: {r.get('source_date') or 'UNKNOWN'}; unknown_date={r['unknown_date']} | staging ID {source['stage_id']}"
            )
        )
    story += [p("Assumptions and unverified attributes", "Heading2")]
    for text in [
        ASSUMPTIONS[1],
        ASSUMPTIONS[2],
        "Geometry types: polygon/multipolygon for parcels and peat; point for substations. No geometry repair performed.",
        f"Unknown source-date flag for candidate: {row['unknown_date']}. Source accuracy and completeness are unverified.",
        "Ownership, planning, grid capacity, connection permission, environmental eligibility and transferability are unverified.",
        "Manifest in this output directory records input/output SHA-256 checksums, all validation evidence and candidate measurements.",
    ]:
        story.append(p(text))
    story += [p("Required uncertainty statement", "Heading2"), p(DISCLAIMER)]

    def footer(c, doc):
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#526470"))
        c.drawString(48, 30, f'IRIS | SYNTHETIC | {row["rule_version"]}')
        c.drawRightString(547, 30, f"{doc.page} / 2")

    SimpleDocTemplate(
        str(path),
        pagesize=(595, 842),
        rightMargin=60,
        leftMargin=60,
        topMargin=40,
        bottomMargin=48,
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    reader = PdfReader(path)
    if len(reader.pages) != 2:
        raise ValueError(f"{path}: expected exactly two pages, got {len(reader.pages)}")
    text = " ".join(" ".join(page.extract_text().split()) for page in reader.pages)
    if DISCLAIMER not in text:
        raise ValueError("Required disclaimer missing from PDF")
