"""
Модуль генерации PDF-комплектов для каждой инстанции согласования.

Для каждой инстанции формирует:
  1. Письмо-запрос (автозаполнение из данных проекта)
  2. Выкопировку из плана трассы (SVG → PDF)
  3. Выписку из кабельного журнала
  4. Список приложений

Выходной файл: один PDF на инстанцию + сводный реестр.
"""

import os, math, tempfile, logging
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm, mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether, Flowable
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfgen import canvas as pdfcanvas

logger = logging.getLogger(__name__)

# ── Шрифты ────────────────────────────────────────────────────────────────────
# Шрифты ищем сначала в папке fonts/ рядом с проектом, затем в системных путях
_HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_BUNDLED = os.path.join(_HERE, "fonts")
_SYS_DJ  = "/usr/share/fonts/truetype/dejavu/"
_SYS_LIB = "/usr/share/fonts/truetype/liberation/"

def _font_path(filename, dirs):
    for d in dirs:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None

_FONTS_OK = False
try:
    dj    = _font_path("DejaVuSans.ttf",            [_BUNDLED, _SYS_DJ])
    dj_b  = _font_path("DejaVuSans-Bold.ttf",       [_BUNDLED, _SYS_DJ])
    dj_i  = _font_path("LiberationSans-Italic.ttf",    [_BUNDLED, _SYS_LIB])
    dj_bi = _font_path("LiberationSans-BoldItalic.ttf",[_BUNDLED, _SYS_LIB])
    djm   = _font_path("DejaVuSansMono.ttf",         [_BUNDLED, _SYS_DJ])
    if not all([dj, dj_b, dj_i, dj_bi, djm]):
        raise FileNotFoundError("Один или несколько шрифтов не найдены")
    pdfmetrics.registerFont(TTFont("DJ",   dj))
    pdfmetrics.registerFont(TTFont("DJ-B", dj_b))
    pdfmetrics.registerFont(TTFont("DJ-I", dj_i))
    pdfmetrics.registerFont(TTFont("DJ-BI",dj_bi))
    pdfmetrics.registerFont(TTFont("DJM",  djm))
    registerFontFamily("DJ", normal="DJ", bold="DJ-B", italic="DJ-I", boldItalic="DJ-BI")
    F, FB, FI, FM = "DJ", "DJ-B", "DJ-I", "DJM"
    _FONTS_OK = True
except Exception as _e:
    logger.warning(f"Шрифты не загружены ({_e}), используется Helvetica")
    F = FB = FI = FM = "Helvetica"

# ── Цвета ─────────────────────────────────────────────────────────────────────
NAVY   = colors.HexColor("#1A2A4A")
BLUE   = colors.HexColor("#2E5C8A")
LBLUE  = colors.HexColor("#D6E4F5")
GREEN  = colors.HexColor("#2E7D32")
LGREEN = colors.HexColor("#E8F5E9")
AMBER  = colors.HexColor("#F57F17")
RED    = colors.HexColor("#C62828")
LGRAY  = colors.HexColor("#F4F6F9")
MGRAY  = colors.HexColor("#B0BEC5")
DGRAY  = colors.HexColor("#455A64")
BORDER = colors.HexColor("#CFD8DC")

# ── Стили ─────────────────────────────────────────────────────────────────────
ss = getSampleStyleSheet()

def _sty(name, **kw):
    return ParagraphStyle(name, parent=ss["Normal"], **{"fontName": F, **kw})

h1_s     = _sty("H1", fontSize=13, fontName=FB, textColor=NAVY,
                spaceBefore=14, spaceAfter=6, leading=17)
h2_s     = _sty("H2", fontSize=11, fontName=FB, textColor=BLUE,
                spaceBefore=10, spaceAfter=4, leading=14)
body_s   = _sty("BD", fontSize=9.5, leading=14, spaceAfter=5, alignment=TA_JUSTIFY)
bullet_s = _sty("BL", fontSize=9.5, leading=13, spaceAfter=3, leftIndent=14)
note_s   = _sty("NT", fontSize=8, fontName=FI, textColor=DGRAY,
                leading=11, spaceAfter=3, leftIndent=8)
th_s     = _sty("TH", fontSize=8.5, fontName=FB, textColor=colors.white,
                alignment=TA_CENTER, leading=11)
td_s     = _sty("TD", fontSize=8.5, leading=11, spaceAfter=1)
td_b_s   = _sty("TB", fontSize=8.5, fontName=FB, leading=11, spaceAfter=1)
cap_s    = _sty("CA", fontSize=8, fontName=FI, textColor=DGRAY,
                alignment=TA_CENTER, spaceAfter=6, spaceBefore=3)

def _th(t): return Paragraph(t, th_s)
def _td(t, b=False): return Paragraph(t, td_b_s if b else td_s)
def _p(t):  return Paragraph(t, body_s)
def _bp(t): return Paragraph(f"\u2022\u00a0\u00a0{t}", bullet_s)
def _sp(h=0.3): return Spacer(1, h*cm)

def _tbl(rows, widths, hc=NAVY):
    t = Table(rows, colWidths=widths)
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0), hc),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[LGRAY, colors.white]),
        ("GRID",(0,0),(-1,-1), 0.4, BORDER),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("TOPPADDING",(0,0),(-1,-1),4),
        ("BOTTOMPADDING",(0,0),(-1,-1),4),
        ("LEFTPADDING",(0,0),(-1,-1),6),
        ("RIGHTPADDING",(0,0),(-1,-1),6),
    ]))
    return t


# ── Canvas с колонтитулами ────────────────────────────────────────────────────
class _HeaderFooterCanvas(pdfcanvas.Canvas):
    def __init__(self, filename, project_name="", instance_name="", **kw):
        super().__init__(filename, **kw)
        self._saved = []
        self._project_name = project_name
        self._instance_name = instance_name

    def showPage(self):
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        n = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw_hf(n)
            super().showPage()
        super().save()

    def _draw_hf(self, total):
        W, _ = A4
        pg = self._pageNumber
        self.setFont(F, 7)
        self.setFillColor(DGRAY)
        self.drawString(2*cm, 1.1*cm,
            f"АС СКЛ · {self._project_name} · {self._instance_name}")
        self.drawRightString(W-2*cm, 1.1*cm, f"Стр. {pg} из {total}")
        self.setStrokeColor(BORDER)
        self.setLineWidth(0.4)
        self.line(2*cm, 1.45*cm, W-2*cm, 1.45*cm)
        # Шапка
        self.setFillColor(NAVY)
        self.rect(0, A4[1]-1.1*cm, W, 1.1*cm, fill=1, stroke=0)
        self.setFillColor(colors.white)
        self.drawString(0.5*cm, A4[1]-0.72*cm, "АС СКЛ")
        self.setFont(F, 7)
        self.setFillColor(colors.HexColor("#A8C4E8"))
        self.drawString(1.8*cm, A4[1]-0.72*cm,
            "Автоматизированная система согласования кабельных линий")


# ── Flowable: схема трассы ───────────────────────────────────────────────────
class RouteSketchFlowable(Flowable):
    """Схема-выкопировка участка трассы для конкретной инстанции."""

    def __init__(self, route, pk_start, pk_end, w, h, intr_type=""):
        super().__init__()
        self.route = route
        self.pk_start = pk_start
        self.pk_end = pk_end
        self.width = w
        self.height = h
        self.intr_type = intr_type

    def draw(self):
        c = self.canv
        W2, H2 = self.width, self.height

        # Фон
        c.setFillColor(colors.HexColor("#EEF2F7"))
        c.rect(0, 0, W2, H2, fill=1, stroke=0)

        # Координатная сетка
        c.setStrokeColor(colors.HexColor("#D0D9EE"))
        c.setLineWidth(0.3)
        for i in range(9):
            c.line(i*W2/8, 0, i*W2/8, H2)
        for j in range(7):
            c.line(0, j*H2/6, W2, j*H2/6)

        # Фильтруем точки в диапазоне пикетов (+ буфер 10%)
        buf = max((self.pk_end - self.pk_start)*0.1, 100)
        pts_in = [p for p in self.route
                  if self.pk_start - buf <= p["pk"] <= self.pk_end + buf]
        if not pts_in:
            pts_in = self.route

        # Масштабирование
        lons = [p["lon"] for p in pts_in if p["lon"]]
        lats = [p["lat"] for p in pts_in if p["lat"]]
        if not lons: return

        pad = 0.6*cm
        min_lon, max_lon = min(lons), max(lons)
        min_lat, max_lat = min(lats), max(lats)
        dlon = max_lon - min_lon or 0.001
        dlat = max_lat - min_lat or 0.001

        def tx(lon): return pad + (lon-min_lon)/dlon*(W2-2*pad)
        def ty(lat): return pad + (lat-min_lat)/dlat*(H2-2*pad)

        # Охранная зона (буфер вокруг трассы)
        c.setStrokeColor(colors.Color(0.88,0.35,0.13,0.18))
        c.setLineWidth(10); c.setLineCap(1)
        path = c.beginPath()
        first = True
        for p in pts_in:
            if p["lon"]:
                x2, y2 = tx(p["lon"]), ty(p["lat"])
                if first: path.moveTo(x2, y2); first=False
                else: path.lineTo(x2, y2)
        c.drawPath(path, stroke=1, fill=0)
        c.setLineCap(0)

        # Трасса
        c.setStrokeColor(colors.HexColor("#E65100"))
        c.setLineWidth(2.2)
        path2 = c.beginPath(); first = True
        for p in pts_in:
            if p["lon"]:
                x2, y2 = tx(p["lon"]), ty(p["lat"])
                if first: path2.moveTo(x2, y2); first=False
                else: path2.lineTo(x2, y2)
        c.drawPath(path2, stroke=1, fill=0)

        # Точки
        for p in pts_in:
            if p["lon"]:
                x2, y2 = tx(p["lon"]), ty(p["lat"])
                c.setFillColor(colors.HexColor("#E65100"))
                c.setStrokeColor(colors.white)
                c.setLineWidth(1)
                c.circle(x2, y2, 3, fill=1, stroke=1)

        # Маркер пересечения
        ix_pt = None
        for p in self.route:
            if abs(p["pk"] - (self.pk_start+self.pk_end)/2) < 200:
                ix_pt = p; break
        if ix_pt and ix_pt.get("lon"):
            ix, iy = tx(ix_pt["lon"]), ty(ix_pt["lat"])
            c.setFillColor(RED)
            c.setStrokeColor(colors.white)
            c.setLineWidth(1.2)
            c.circle(ix, iy, 7, fill=1, stroke=1)
            c.setFillColor(colors.white); c.setFont(FB, 8)
            c.drawCentredString(ix, iy-3, "!")

        # Пикеты
        for p in pts_in:
            if p["lon"] and p["pk"] % 500 < 100:
                x2, y2 = tx(p["lon"]), ty(p["lat"])
                pk = int(p["pk"])
                c.setFillColor(NAVY); c.setFont(FM, 5.5)
                c.drawString(x2+4, y2+4, f"ПК {pk//1000}+{pk%1000:03d}")

        # Компас
        c.setFillColor(colors.white); c.setStrokeColor(MGRAY); c.setLineWidth(0.6)
        c.circle(W2-1.4*cm, 1.4*cm, 0.9*cm, fill=1, stroke=1)
        c.setFillColor(RED); c.setFont(FB, 7)
        c.drawCentredString(W2-1.4*cm, 2.0*cm, "С")
        c.setStrokeColor(RED); c.setLineWidth(1.5)
        c.line(W2-1.4*cm, 1.9*cm, W2-1.4*cm, 2.2*cm)
        c.setStrokeColor(MGRAY); c.setLineWidth(1)
        c.line(W2-1.4*cm, 1.5*cm, W2-1.4*cm, 0.9*cm)

        # Рамка
        c.setStrokeColor(NAVY); c.setLineWidth(1.2)
        c.rect(0, 0, W2, H2, fill=0, stroke=1)

        # Штамп
        c.setFillColor(LGRAY); c.setStrokeColor(BORDER); c.setLineWidth(0.5)
        c.rect(0, 0, W2, 1.2*cm, fill=1, stroke=1)
        c.setFillColor(NAVY); c.setFont(FB, 7)
        c.drawString(0.3*cm, 0.8*cm, "ВЫКОПИРОВКА ИЗ ПЛАНА ТРАССЫ КЛ")
        c.setFont(F, 6.5); c.setFillColor(DGRAY)
        c.drawString(0.3*cm, 0.3*cm,
            f"ПК {int(self.pk_start)//1000}+{int(self.pk_start)%1000:03d} — "
            f"ПК {int(self.pk_end)//1000}+{int(self.pk_end)%1000:03d}  |  М 1:1 000  |  АС СКЛ")


# ── Главный генератор ─────────────────────────────────────────────────────────
class PDFGenerator:

    PRIORITY_COLORS = {
        "critical":    colors.HexColor("#FFEBEE"),
        "important":   colors.HexColor("#FFF3E0"),
        "recommended": colors.HexColor("#F5F5F5"),
    }
    PRIORITY_LABELS = {
        "critical": "● Критично",
        "important": "● Важно",
        "recommended": "○ Рекомендуется",
    }

    def generate_package(self, project: dict,
                         approval_ids=None) -> str:
        """
        Генерирует полный PDF-пакет согласований.
        Возвращает путь к файлу.
        """
        cad = project.get("cadastral_result", {})
        approvals = cad.get("approvals", [])
        if approval_ids:
            approvals = [a for a in approvals if a["id"] in approval_ids]

        out_dir = tempfile.mkdtemp()
        out_path = os.path.join(out_dir,
            f"АС_СКЛ_{project['name'].replace(' ','_')}.pdf")

        route = project.get("route", [])
        doc = SimpleDocTemplate(
            out_path, pagesize=A4,
            leftMargin=2*cm, rightMargin=2*cm,
            topMargin=2.5*cm, bottomMargin=2*cm,
            title=f"АС СКЛ · {project['name']}",
        )

        story = []

        # ── Титульный лист пакета ────────────────────────────────────────────
        story += self._title_page(project, approvals)
        story.append(PageBreak())

        # ── Реестр согласований ──────────────────────────────────────────────
        story += self._registry_page(project, approvals)
        story.append(PageBreak())

        # ── Письмо + приложения для каждой инстанции ────────────────────────
        for i, approval in enumerate(approvals):
            story += self._approval_letter(project, approval, route)
            story += self._approval_attachments(project, approval, route)
            if i < len(approvals)-1:
                story.append(PageBreak())

        def make_canvas(filename, **kw):
            return _HeaderFooterCanvas(
                filename,
                project_name=project["name"],
                instance_name="Комплект согласований",
                **kw
            )

        doc.build(story, canvasmaker=make_canvas)
        logger.info(f"PDF generated: {out_path}")
        return out_path

    # ── Приватные методы ──────────────────────────────────────────────────────

    def _title_page(self, project, approvals):
        story = []
        story.append(_sp(1))
        story.append(Paragraph(
            "КОМПЛЕКТ ДОКУМЕНТОВ ДЛЯ СОГЛАСОВАНИЯ", _sty("T",
            fontSize=16, fontName=FB, textColor=NAVY, alignment=TA_CENTER,
            spaceAfter=8, leading=22)))
        story.append(Paragraph(
            f"Проект: <b>{project['name']}</b>", _sty("ST",
            fontSize=12, alignment=TA_CENTER, spaceAfter=6, leading=16)))
        story.append(HRFlowable(width="60%", thickness=2, color=BLUE,
                                hAlign="CENTER", spaceAfter=16))
        story.append(_sp(0.5))

        meta = [
            [_th("Параметр"), _th("Значение")],
            [_td("Заказчик",True), _td("ООО «Электромонтаж-110»")],
            [_td("Наименование объекта",True), _td(project["name"])],
            [_td("Протяжённость трассы",True),
             _td(f"{project.get('total_length_m',0):.0f} м")],
            [_td("Система координат",True), _td(project.get("crs","—"))],
            [_td("Дата формирования",True),
             _td(date.today().strftime("%d.%m.%Y"))],
            [_td("Сформировано",True), _td("АС СКЛ v2.0 — автоматически")],
        ]
        story.append(_tbl(meta, [6*cm, 10.5*cm]))
        story.append(_sp(0.8))

        # Сводка
        critical = sum(1 for a in approvals if a["priority"]=="critical")
        important = sum(1 for a in approvals if a["priority"]=="important")
        days = max(((a["review_days"] or 0) for a in approvals
                    if a["priority"]=="critical"), default=0)
        stats = [
            [_th("Всего"), _th("Критично"), _th("Важно"), _th("Критич. путь")],
            [_td(str(len(approvals)),False), _td(str(critical),False),
             _td(str(important),False), _td(f"{days} дн.",False)],
        ]
        t = _tbl(stats, [3.5*cm,3.5*cm,3.5*cm,6*cm], hc=BLUE)
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),BLUE),
            ("GRID",(0,0),(-1,-1),0.4,BORDER),
            ("ALIGN",(0,0),(-1,-1),"CENTER"),
            ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
            ("TOPPADDING",(0,0),(-1,-1),8),
            ("BOTTOMPADDING",(0,0),(-1,-1),8),
        ]))
        story.append(t)
        story.append(_sp(0.5))
        story.append(Paragraph(
            "Документ сформирован автоматически системой АС СКЛ. "
            "Все письма требуют проверки инженером по согласованиям "
            "перед отправкой.", note_s))
        return story

    def _registry_page(self, project, approvals):
        story = []
        story.append(Paragraph("РЕЕСТР СОГЛАСОВАНИЙ", h1_s))
        story.append(HRFlowable(width="100%", thickness=1.2,
                                color=BLUE, spaceAfter=8))

        rows = [[_th("№"), _th("Инстанция"), _th("Основание"),
                 _th("Срок, дн."), _th("Приоритет"), _th("Статус"),
                 _th("Приложений")]]
        for a in approvals:
            pcolor = {
                "critical": RED, "important": AMBER,
            }.get(a["priority"], DGRAY)
            plbl = self.PRIORITY_LABELS.get(a["priority"], a["priority"])
            rows.append([
                _td(str(a["id"]),True),
                _td(a["instance_name"]),
                _td(a["legal_basis"]),
                _td(str(a["review_days"] or "—")),
                Paragraph(plbl, _sty("PL", fontSize=8, fontName=FB,
                                     textColor=pcolor, leading=10)),
                _td(a.get("status","pending")),
                _td(str(len(a.get("attachments",[]))))
            ])

        t = _tbl(rows, [0.8*cm,4*cm,2.2*cm,1.5*cm,2.2*cm,1.8*cm,1.5*cm])
        story.append(t)
        story.append(_sp(0.3))
        story.append(Paragraph(
            f"Сформировано: {date.today().strftime('%d.%m.%Y')} · "
            f"Источник: АС СКЛ v2.0 · Заказчик: ООО «Электромонтаж-110»",
            note_s))
        return story

    def _approval_letter(self, project, approval, route):
        story = []
        story.append(Paragraph(
            f"ПИСЬМО-ЗАПРОС № {approval['id']}", h1_s))
        story.append(HRFlowable(width="100%", thickness=1.2,
                                color=BLUE, spaceAfter=10))

        # Шапка письма
        letter_meta = [
            [_th("Поле"), _th("Значение (автозаполнено)")],
            [_td("Кому",True),
             _td(f"{approval['instance_name']} · руководителю")],
            [_td("От кого",True),
             _td("ООО «Электромонтаж-110» (ИНН 7701234567, ОГРН 1157746123456)")],
            [_td("Исх. №",True),
             _td(f"ЭМ110-{date.today().year}-{approval['id']:04d}")],
            [_td("Дата",True), _td(date.today().strftime("%d.%m.%Y"))],
            [_td("Тема",True),
             _td(f"Согласование кабельной линии · {approval['intersection_ref']}")],
            [_td("Правовое основание",True), _td(approval["legal_basis"])],
        ]
        story.append(_tbl(letter_meta, [3*cm,13.5*cm], hc=BLUE))
        story.append(_sp(0.4))

        # Тело письма
        story.append(_p(
            f"ООО «Электромонтаж-110» направляет настоящее письмо с просьбой "
            f"согласовать пересечение (сближение) проектируемой кабельной линии "
            f"с объектом, находящимся в вашем ведении."
        ))
        story.append(_p(
            f"<b>Объект:</b> {project['name']} · "
            f"<b>Участок:</b> {approval['intersection_ref']}"
        ))
        story.append(_p(
            f"Протяжённость трассы: {project.get('total_length_m',0):.0f} м. "
            f"Прокладка кабеля предусмотрена в траншее глубиной 1.2–1.5 м "
            f"и методом ГНБ на пересечениях с дорогами и коммуникациями."
        ))
        story.append(_sp(0.3))

        # Перечень приложений
        story.append(Paragraph("Приложения:", h2_s))
        for i, att in enumerate(approval.get("attachments",[]), 1):
            story.append(_bp(f"{i}. {att}"))

        story.append(_sp(0.5))
        story.append(_p("С уважением,"))
        story.append(_sp(0.1))
        story.append(_p("<b>Генеральный директор ООО «Электромонтаж-110»</b>"))
        story.append(_p("_________________ / ______________ /"))
        story.append(_sp(0.3))
        story.append(Paragraph(
            "⚠ Поле подписи и исходящий номер требуют ручного заполнения.",
            note_s))
        return story

    def _approval_attachments(self, project, approval, route):
        story = []
        story.append(_sp(0.5))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=BORDER, spaceAfter=8))
        story.append(Paragraph(
            f"ПРИЛОЖЕНИЯ к письму инстанции: {approval['instance_name']}",
            h2_s))

        # 1. Выкопировка из плана
        if "Выкопировка" in " ".join(approval.get("attachments",[])):
            story.append(Paragraph(
                "Приложение 1. Выкопировка из плана трассы", h2_s))
            # Рисуем схему участка
            intr = self._find_intersection(approval, project)
            pk_s = intr.get("pk_start", 0) if intr else 0
            pk_e = intr.get("pk_end", 500) if intr else 500
            buf = max((pk_e - pk_s) * 0.5, 300)
            sketch = RouteSketchFlowable(
                route=route,
                pk_start=max(0, pk_s - buf),
                pk_end=pk_e + buf,
                w=16.5*cm, h=8*cm,
                intr_type=intr.get("object_type","") if intr else "",
            )
            story.append(sketch)
            story.append(Paragraph(
                f"Рис. Выкопировка из плана трассы КЛ · "
                f"ПК {int(pk_s)//1000}+{int(pk_s)%1000:03d} — "
                f"ПК {int(pk_e)//1000}+{int(pk_e)%1000:03d} · М 1:1 000",
                cap_s))
            story.append(_sp(0.3))

        # 2. Выписка из кабельного журнала (таблица по участку)
        if "Выписка" in " ".join(approval.get("attachments",[])) or \
           "журнал" in " ".join(approval.get("attachments",[])).lower():
            story.append(Paragraph(
                "Приложение 2. Выписка из кабельного журнала", h2_s))
            intr = self._find_intersection(approval, project)
            pk_s2 = intr.get("pk_start",0) if intr else 0
            pk_e2 = intr.get("pk_end",project.get("total_length_m",0)) if intr else 9999
            cable_rows = [[_th("№"), _th("Участок"), _th("Марка кабеля"),
                           _th("U, кВ"), _th("Сечение"), _th("Длина, м"),
                           _th("Способ"), _th("Глуб., м")]]
            seg = 1
            for i, pt in enumerate(route[:-1]):
                if pt["pk"] >= pk_s2 - 50 and route[i+1]["pk"] <= pk_e2 + 50:
                    length = round(route[i+1]["pk"] - pt["pk"], 0)
                    cable_rows.append([
                        _td(str(seg),True),
                        _td(f"ПК {int(pt['pk'])//1000}+{int(pt['pk'])%1000:03d} → "
                            f"ПК {int(route[i+1]['pk'])//1000}+{int(route[i+1]['pk'])%1000:03d}"),
                        _td("ААБ2л-10"), _td("10"), _td("3×185"),
                        _td(str(length)), _td("Траншея"),
                        _td(str(pt.get("depth",1.2))),
                    ])
                    seg += 1
            if len(cable_rows) > 1:
                story.append(_tbl(cable_rows,
                    [0.7*cm,3.5*cm,2*cm,1*cm,1.3*cm,1.5*cm,1.8*cm,1.2*cm]))
            story.append(_sp(0.3))

        return story

    def _find_intersection(self, approval, project):
        """Находит пересечение, соответствующее данной инстанции."""
        cad = project.get("cadastral_result", {})
        for intr in cad.get("intersections", []):
            if intr.get("cadastral_number") and \
               intr["cadastral_number"] in approval.get("intersection_ref",""):
                return intr
            if intr.get("object_type") in approval.get("intersection_ref","").lower():
                return intr
        intrs = cad.get("intersections", [])
        return intrs[0] if intrs else None
