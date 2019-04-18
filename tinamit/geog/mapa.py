import numpy as np
import shapefile as sf
from matplotlib import colors, cm
from matplotlib.backends.backend_agg import FigureCanvasAgg as TelaFigura
from matplotlib.figure import Figure as Figura

from tinamit.config import _


class Mapa(object):
    def __init__(símismo, formas):
        símismo.formas = formas

    def dibujar(símismo, archivo=None, título=None):

        fig = Figura()
        TelaFigura(fig)
        ejes = fig.add_subplot(111)
        ejes.set_aspect('equal')

        for frm in símismo.formas:
            frm.dibujar(ejes, fig)
        if título is not None:
            ejes.set_title(título)
        if archivo:
            fig.savefig(archivo, dpi=500)

        return ejes


class Forma(object):
    def __init__(símismo, archivo, llenar, alpha):
        símismo.forma = sf.Reader(archivo)
        símismo.llenar = llenar
        símismo.alpha = alpha

    def dibujar(símismo, ejes, fig):
        raise NotImplementedError

    def _dibujar_frm(símismo, ejes, color):
        for i, frm in enumerate(símismo.forma.shapes()):
            puntos = frm.points
            partes = frm.parts

            for ip, i0 in enumerate(partes):  # Para cada parte del imagen

                if ip < len(partes) - 1:
                    i1 = partes[ip + 1] - 1
                else:
                    i1 = len(puntos)

                seg = puntos[i0:i1 + 1]
                x_lon = np.zeros((len(seg), 1))
                y_lat = np.zeros((len(seg), 1))
                for i in range(len(seg)):
                    x_lon[i] = seg[i][0]
                    y_lat[i] = seg[i][1]

                clr = color[i] if isinstance(color, np.ndarray) else color
                if símismo.llenar:
                    ejes.fill(x_lon, y_lat, color=clr, alpha=símismo.alpha)
                else:
                    ejes.plot(x_lon, y_lat, color=clr, alpha=símismo.alpha)


class FormaEstática(Forma):
    def __init__(símismo, archivo, color, llenar, alpha):
        símismo.color = color
        super().__init__(archivo, llenar=llenar, alpha=alpha)

    def dibujar(símismo, ejes, fig):
        símismo._dibujar_frm(ejes, color=símismo.color)


class FormaDinámica(Forma):
    def __init__(símismo, archivo, col_id, escala_colores=None, llenar=True, alpha=1):
        super().__init__(archivo, llenar=llenar, alpha=alpha)

        símismo.col_id = col_id
        símismo.escala_colores = símismo._resolver_colores(escala_colores)
        símismo.valores = np.full(len(símismo.forma.shapes()), np.nan)
        símismo.unidades = None
        símismo.escala = None

        nombres_attr = [field[0] for field in símismo.forma.fields[1:]]
        try:
            símismo.ids = [x.record[nombres_attr.index(símismo.col_id)] for x in símismo.forma.shapeRecords()]
        except ValueError:
            raise ValueError(_('La columna "{}" no existe en la base de datos.').format(símismo.col_id))

    def estab_valores(símismo, valores, escala=None, unidades=None):
        símismo.unidades = unidades

        if isinstance(valores, dict):
            símismo.valores[:] = np.nan
            for id_, val in valores.items():
                i = símismo.ids.index(id_)
                símismo.valores[i] = val
        else:
            símismo.valores[:] = valores

        if escala is None:
            if np.all(np.isnan(símismo.valores)):
                escala = (0, 1)
            else:
                escala = (np.nanmin(símismo.valores), np.nanmax(símismo.valores))
                if escala[0] == escala[1]:
                    escala = (escala[0] - 0.5, escala[0] + 0.5)

        símismo.escala = escala

    def dibujar(símismo, ejes, fig):
        vals_norm = (símismo.valores - símismo.escala[0]) / (símismo.escala[1] - símismo.escala[0])

        d_clrs = _gen_d_mapacolores(colores=símismo.escala_colores)

        mapa_color = colors.LinearSegmentedColormap('mapa_color', d_clrs)
        norm = colors.Normalize(vmin=símismo.escala[0], vmax=símismo.escala[1])
        cpick = cm.ScalarMappable(norm=norm, cmap=mapa_color)
        cpick.set_array(np.array([]))

        v_cols = mapa_color(vals_norm)
        v_cols[np.isnan(vals_norm)] = 0

        símismo._dibujar_frm(ejes=ejes, color=v_cols)

        if símismo.unidades is not None:
            fig.colorbar(cpick, label=símismo.unidades)
        else:
            fig.colorbar(cpick)

    @staticmethod
    def _resolver_colores(colores):
        if colores is None:
            return ['#FF6666', '#FFCC66', '#00CC66']
        elif colores == -1:
            return ['#00CC66', '#FFCC66', '#FF6666']
        elif isinstance(colores, str):
            return ['#FFFFFF', colores]
        return colores


class Agua(FormaEstática):
    def __init__(símismo, archivo):
        super().__init__(archivo=archivo, color='#A5BFDD', llenar=True, alpha=0.5)


class Calle(FormaEstática):
    def __init__(símismo, archivo):
        super().__init__(archivo=archivo, color='#A5BFDD', llenar=False, alpha=1)


class Ciudad(FormaEstática):
    def __init__(símismo, archivo):
        super().__init__(archivo=archivo, color='#FB9A99', llenar=True, alpha=1)


class Bosque(FormaEstática):
    def __init__(símismo, archivo):
        super().__init__(archivo=archivo, color='#33A02C', llenar=True, alpha=0.7)


class OtraForma(FormaEstática):
    def __init__(símismo, archivo):
        super().__init__(archivo=archivo, color='#FFECB3', llenar=True, alpha=1)


def _hex_a_rva(hx):
    """
    Convierte colores RVA a Hex.

    Parameters
    ----------
    hx: str
        El valor hex.

    Returns
    -------
    tuple
        El valor rva.
    """
    return tuple(int(hx.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))


def _gen_d_mapacolores(colores):
    """
    Genera un diccionario de mapa de color para MatPlotLib.

    Parameters
    ----------
    colores: list
        Una lista de colores

    Returns
    -------
    dict
        Un diccionario para MatPlotLib
    """

    clrs_rva = [_hex_a_rva(x) for x in colores]
    # noinspection PyTypeChecker
    n_colores = len(colores)

    dic_c = {'red': tuple((round(i / (n_colores - 1), 2), clrs_rva[i][0] / 255, clrs_rva[i][0] / 255) for i in
                          range(0, n_colores)),
             'green': tuple(
                 (round(i / (n_colores - 1), 2), clrs_rva[i][1] / 255, clrs_rva[i][1] / 255) for i in
                 range(0, n_colores)),
             'blue': tuple(
                 (round(i / (n_colores - 1), 2), clrs_rva[i][2] / 255, clrs_rva[i][2] / 255) for i in
                 range(0, n_colores))}

    return dic_c
