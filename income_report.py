from html import escape
from io import BytesIO

import altair as alt
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate


def build_ranking_pdf(metadata, country_names, age_text, sections):
    filters = metadata["filters"]
    source = metadata["source"]
    chart_year = filters["survey_years"][-1]
    years_text = ", ".join(map(str, filters["survey_years"]))
    sex_text = ", ".join(section["label"] for section in sections)
    units_text = " and ".join(filters["units"])

    output = BytesIO()
    title = "EURO_DATA | EUR and PPS ranking report"
    document = SimpleDocTemplate(
        output, pagesize=landscape(A4), title=title,
        leftMargin=36, rightMargin=36, topMargin=32, bottomMargin=34,
    )
    styles = getSampleStyleSheet()
    ink = HexColor("#17354F")
    styles["Title"].alignment = TA_LEFT
    styles["Title"].textColor = ink
    styles["Heading2"].textColor = ink

    def line(text, style="BodyText"):
        return Paragraph(escape(text.replace("–", "-")), styles[style])

    story = [
        line(title, "Title"),
        line(f"{filters['statinfo_label']} | Survey year {chart_year}", "Heading2"),
        line("Applied filters", "Heading3"),
        line("Countries | " + ", ".join(country_names)),
        line(f"Age {age_text} | Sex {sex_text} | Units {units_text}"),
        line(f"{filters['year_selection']} | Survey years {years_text}"),
        line(f"Ranking sample | {filters['ranking_sample_label']}"),
    ]

    tall_figures = []
    for section in sections:
        label = section["label"]
        group = [line(f"{label} | Summary", "Heading2"), line(section["summary"])]
        chart = section["chart"]
        if chart is not None:
            # Preserve the plotted values and use closer rows on the printed page.
            panels = [panel.properties(height=alt.Step(22)) for panel in chart.hconcat]
            print_chart = chart.properties(title=f"{label} | Survey year {chart_year}")
            print_chart.hconcat = panels

            chart_buffer = BytesIO()
            print_chart.save(chart_buffer, format="png", scale_factor=2)
            chart_buffer.seek(0)
            figure = Image(chart_buffer)
            fit = min(
                (document.width - 12) / figure.imageWidth,
                (document.height - 20) / figure.imageHeight,
            )
            figure.drawWidth = fit * figure.imageWidth
            figure.drawHeight = fit * figure.imageHeight
            figure.hAlign = "LEFT"
            if figure.drawHeight > document.height / 2:
                tall_figures.append(figure)
            else:
                group.append(figure)
        story.append(KeepTogether(group))

        rows = section["rows"]
        excluded = rows.loc[rows["rank_EUR"].isna(), ["geo_label", "rank_status"]]
        if not excluded.empty:
            names = [
                f"{name} ({status})"
                for name, status in excluded.itertuples(index=False, name=None)
            ]
            story.append(line("Excluded | " + ", ".join(names)))

        flags = rows[["geo_label", "flag_EUR", "flag_PPS"]].fillna("")
        flag_notes = []
        for name, eur_flag, pps_flag in flags.itertuples(index=False, name=None):
            codes = [
                f"{unit} {flag}"
                for unit, flag in (("EUR", eur_flag), ("PPS", pps_flag))
                if flag
            ]
            if codes:
                flag_notes.append(f"{name} ({', '.join(codes)})")
        if flag_notes:
            story.append(line("Eurostat flags | " + ", ".join(flag_notes)))

    if filters["ranking_sample"] == "common":
        sample_note = "The common sample requires EUR and PPS data in every applied survey year."
    else:
        sample_note = "Each year uses countries with both units available. Sample membership may vary by year."

    source_url = escape(source["request_url"], quote=True)
    source_label = escape(
        f"{source['provider']} | Dataset {source['dataset']} | Delivery {source['delivery']}"
    )
    updated_at = source.get("updated_at") or "Unavailable"
    notes = [
        line("Source and interpretation", "Heading2"),
        Paragraph(
            f'{source_label} | <link href="{source_url}" color="#216698">Open API response</link>',
            styles["BodyText"],
        ),
        line(f"Retrieved UTC {source['retrieved_at_utc']} | Eurostat updated {updated_at}"),
        line(sample_note),
        line(
            "Rank change is the EUR rank minus the PPS rank in the same survey year. "
            f"{metadata['csv']['ties']}"
        ),
        line("The income axes use separate scales. Diamonds mark flags. Flag b marks a break in the series."),
    ]
    story.append(KeepTogether(notes))
    story.extend(tall_figures)

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(ink)
        canvas.drawString(doc.leftMargin, 19, "EURO_DATA | Income explorer")
        page_width = doc.pagesize[0]
        canvas.drawRightString(page_width - doc.rightMargin, 19, f"Page {doc.page}")

    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()