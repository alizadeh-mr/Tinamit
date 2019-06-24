import datetime as ft
import pickle
from multiprocessing import Pool as Reserva
from warnings import warn as avisar

import numpy as np
import pandas as pd

from tinamit.config import _, conf_mods
from tinamit.cositas import guardar_json, cargar_json
from .corrida import Corrida, Rebanada
from .extern import gen_extern
from .res import ResultadosGrupo
from .tiempo import EspecTiempo
from .vars_mod import VariablesMod

def jsonificar(o):
    if isinstance(o, dict):
        for ll, v in o.items():
            if isinstance(v, (dict, list)):
                jsonificar(v)
            elif isinstance(v, (ft.date, ft.datetime)):
                o[ll] = str(v)
            elif isinstance(v, np.ndarray):
                o[ll] = v.tolist()
    elif isinstance(o, list):
        for i, v in enumerate(o):
            if isinstance(v, (dict, list)):
                jsonificar(v)
            elif isinstance(v, (ft.date, ft.datetime)):
                o[i] = str(v)
            elif isinstance(v, np.ndarray):
                o[i] = v.tolist()


def numpyficar(d):
    for ll, v in d.items():
        if isinstance(v, dict):
            numpyficar(v)
        elif isinstance(v, list):
            try:
                d[ll] = np.array(v, dtype=float)
            except ValueError:
                pass
class Modelo(object):
    """
    Todas las cosas en Tinamit son instancias de `Modelo`, que sea un modelo de dinámicas de los sistemas, un modelo de
    cultivos o de suelos o de clima, o un modelo conectado.
    Cada tipo de modelo se representa por subclases específicas. Por eso, la gran mayoría de los métodos definidos
    aquí se implementan de manera independiente en cada subclase de `Modelo`.
    """

    idioma_orig = 'es'  # Cambiar en tu modelo si el idioma de sus variables, etc. no es el castellano

    def __init__(símismo, variables, nombre):
        """
        La función de inicialización de todos modelos, conectados o no.

        Parameters
        ----------
        variables : VariablesMod
            Los variables del modelo.
        nombre : str
            El nombre del modelo.

        """

        símismo.nombre = nombre
        símismo.variables = variables
        símismo.corrida = None

    def unidad_tiempo(símismo):
        """
        Esta función debe devolver la unidad de tiempo empleada por el modelo.

        Returns
        -------
        str
            La unidad de tiempo (p. ej., 'meses', 'مہینہ', etc.)
        """

        raise NotImplementedError

    def simular(símismo, t, nombre='Tinamït', vals_extern=None, clima=None, vars_interés=None):
        if not isinstance(t, EspecTiempo):
            t = EspecTiempo(t)

        corrida = Corrida(
            nombre, t=t.gen_tiempo(símismo.unidad_tiempo()),
            extern=gen_extern(vals_extern),
            vars_mod=símismo.variables,
            vars_interés=vars_interés
        )

        símismo.iniciar_modelo(corrida)
        símismo.correr()
        símismo.cerrar()

        return corrida.resultados

    def simular_grupo(símismo, ops_grupo, nombre='Tinamït', paralelo=False):

        if paralelo and not símismo.paralelizable():
            avisar(_(
                '\nEl modelo no se identifica como paralelizable. Para evitar el riesgo'
                '\nde errores de paralelización, correremos las corridas como simulaciones secuenciales '
                '\nnormales. '
                '\nSi tu modelo sí es paralelizable, crear un método nombrado `.paralelizable()` '
                '\nque devuelve ``True`` en tu clase de modelo para activar la paralelización.'
            ))
            paralelo = False

        res_grupo = ResultadosGrupo(nombre)
        if paralelo:
            l_trabajos = []
            copia_mod = pickle.dumps(símismo)  # Una copia de este modelo.

            # Crear la lista de información necesaria para las simulaciones en paralelo...
            for ops in ops_grupo:
                l_trabajos.append((copia_mod, ops))

            # Hacer las corridas en paralelo
            with Reserva() as r:
                res_paralelo = r.map(_correr_modelo, l_trabajos)
            for res in res_paralelo:
                res_grupo[str(res)] = res

        else:
            for ops in ops_grupo:
                res = símismo.simular(**ops)
                res_grupo[str(res)] = res

        return res_grupo

    def iniciar_modelo(símismo, corrida):  # para hacer: super() en subclasses
        símismo.corrida = corrida
        corrida.variables.reinic()

        if corrida.extern:
            símismo.cambiar_vals({vr: vl.values for vr, vl in corrida.obt_extern_act().items() if vr in símismo.variables})
        corrida.actualizar_res()

    def correr(símismo):
        intento = símismo._correr_hasta_final()
        if intento is not None:
            símismo.corrida.resultados.poner_vals_t(intento)
        else:
            while símismo.corrida.t.avanzar():
                símismo.incrementar(
                    Rebanada(
                        símismo.corrida.t.pasos_avanzados(símismo.unidad_tiempo()),
                        resultados=símismo.corrida.resultados
                    )
                )
                símismo.corrida.actualizar_res()

    def _correr_hasta_final(símismo):
        return None

    def incrementar(símismo, rebanada):
        if símismo.corrida.extern:
            símismo.cambiar_vals({vr: vl.values for vr, vl in símismo.corrida.obt_extern_act().items()})

    def cerrar(símismo):
        """
        Esta función debe tomar las acciones necesarias para terminar la simulación y cerrar el modelo, si aplica.
        Si no aplica, usar ``pass``.
        """
        pass

    def cambiar_vals(símismo, valores):
        """
        Esta función cambia el valor de uno o más variables del modelo.

        Parameters
        ----------
        valores : dict
            Un diccionario de variables y sus valores para cambiar.
        """

        # Cambia primero el valor en el diccionario interno del Modelo
        símismo.variables.cambiar_vals(valores=valores)

    @classmethod
    def obt_conf(cls, llave, auto=None, cond=None, mnsj_err=None):

        auto = auto or []
        if isinstance(auto, str):
            auto = [auto]

        try:
            op = conf_mods[cls.__name__][llave]
            if cond is None or cond(op):
                return op
        except KeyError:
            pass

        for op in auto:
            if cond is None or cond(op):
                conf_mods[cls.__name__][llave] = op
                return op

        if mnsj_err:
            avisar(mnsj_err)

    @classmethod
    def estab_conf(cls, llave, valor):
        conf_mods[cls.__name__, llave] = valor

    @classmethod
    def instalado(cls):
        """
        Si tu modelo depiende en una instalación de otro programa externo a Tinamït, puedes reimplementar esta función
        para devolver ``True`` si el modelo está instalado y ``False`` sino.

        Returns
        -------
        bool
            Si el modelo está instalado completamente o no.
        """

        return True

    def paralelizable(símismo):
        """
        Indica si el modelo actual se puede paralelizar de manera segura o no. Si implementas una subclase
        paralelizable, reimplementar esta función para devolver ``True``.
        ¿No sabes si es paralelizable tu modelo?
        Si el modelo se puede paralelizar (con corridas de nombres distintos) sin encontrar dificultades
        técnicas (sin riesgo que las corridas paralelas terminen escribiendo en los mismos archivos de egreso),
        entonces sí es paralelizable tu modelo.

        Returns
        -------
        bool:
            Si el modelo es paralelizable o no.
        """

        return False

    def __str__(símismo):
        return símismo.nombre

    # para hacer:
    def conectar_var_clima(símismo, var, var_clima, conv, combin=None):
        """
        Conecta un variable climático.

        Parameters
        ----------
        var : str
            El nombre interno del variable en el modelo.
        var_clima : str
            El nombre oficial del variable climático.
        conv : number
            La conversión entre el variable clima en Tinamït y el variable correspondiente en el modelo.
        combin : str
            Si este variable se debe adicionar o tomar el promedio entre varios pasos.
        """

        var = símismo.valid_var(var)

        if var_clima not in Geog.conv_vars:
            raise ValueError(_('El variable climático "{}" no es una posibilidad. Debe ser uno de:\n'
                               '\t{}').format(var_clima, ', '.join(Geog.conv_vars)))

        if combin not in ['prom', 'total', None]:
            raise ValueError(_('"Combin" debe ser "prom", "total", o None, no "{}".').format(combin))

        símismo.vars_clima[var] = {
            'nombre_extrn': var_clima,
            'combin': combin,
            'conv': conv
        }

    def desconectar_var_clima(símismo, var):
        """
        Esta función desconecta un variable climático.

        Parameters
        ----------
        var : str
            El nombre interno del variable en el modelo.

        """

        símismo.vars_clima.pop(var)

    def _act_vals_clima(símismo, f_0, f_1, lugar):
        """
        Actualiza los variables climáticos. Esta función es la automática para cada modelo. Si necesitas algo más
        complicado (como, por ejemplo, predicciones por estación), la puedes cambiar en tu subclase.

        Parameters
        ----------
        f_0 : ft.date | ft.datetime
            La fecha actual.
        f_1 : ft.date | ft.datetime
            La próxima fecha.
        lugar : Lugar
            El objeto `Lugar` del cual obtendremos el clima.

        """

        # Si no tenemos variables de clima, no hay nada que hacer.
        if not len(símismo.vars_clima):
            return

        # Avisar si arriesgamos perder presición por combinar datos climáticos.
        n_días = int((f_1 - f_0) / np.timedelta64(1, 'D'))
        if n_días > 1:
            avisar('El paso es de {} días. Puede ser que las predicciones climáticas pierdan '
                   'en precisión.'.format(n_días))

        # Correspondencia entre variables climáticos y sus nombres en el modelo.
        nombres_extrn = [d['nombre_extrn'] for d in símismo.vars_clima.values()]

        # La lista de maneras de combinar los valores diarios
        combins = [d['combin'] for d in símismo.vars_clima.values()]

        # La lista de factores de conversión
        convs = [d['conv'] for d in símismo.vars_clima.values()]

        # Calcular los datos
        datos = lugar.comb_datos(vars_clima=nombres_extrn, combin=combins, f_inic=f_0, f_final=f_1)

        # Aplicar los valores de variables calculados
        for i, var in enumerate(símismo.vars_clima):
            # Para cada variable en la lista de clima...

            # El nombre oficial del variable de clima
            var_clima = nombres_extrn[i]

            # El factor de conversión de unidades
            conv = convs[i]

            # Aplicar el cambio
            símismo.cambiar_vals(valores={var: datos[var_clima] * conv})

    def _obt_vars_asociados(símismo, var, bd=None, enforzar_datos=False, incluir_hermanos=False):
        """
        Obtiene los variables asociados con un variable de interés.

        Parameters
        ----------
        var : str
            El variable de interés.
        enforzar_datos : bool
            Si buscamos únicamente variables que tienen datos en la base de datos vinculada.
        incluir_hermanos :
            Si incluyemos los hermanos del variable (es decir, otros variables que se computan a base de los parientes
            del variable de interés.

        Returns
        -------
        set
            El conjunto de todos los variables vinculados.

        Raises
        ------
        ValueError
            Si no todos los variables asociados tienen ecuación especificada.
        RecursionError
            Si `enforzar_datos == True` y no hay suficientemente datos disponibles para encontrar parientes con datos
            para todos los variables asociados con el variable de interés.
        """

        # La base de datos
        bd_datos = bd if enforzar_datos else None

        # El diccionario de variables
        d_vars = símismo.variables

        # Una función recursiva queda muy útil en casos así.
        def _sacar_vars_recurs(v, c_v=None, sn_dts=None):
            """
            Una función recursiva para sacar variables asociados con un variable de interés.
            Parameters
            ----------
            v : str
                El variable de interés.
            c_v : set
                El conjunto de variables asociados (parámetro de recursión).

            Returns
            -------
            set
                El conjunto de variables asociados.

            """

            # Para evitar problemas de recursión en Python.
            if c_v is None:
                c_v = set()
            if sn_dts is None:
                sn_dts = set()

            # Verificar que el variable tenga ecuación
            if 'ec' not in d_vars[v]:
                raise ValueError(_('El variable "{}" no tiene ecuación.').format(v))

            # Los parientes del variable
            parientes = d_vars[v]['parientes']

            # Agregar los parientes al conjunto de variables vinculados
            c_v.update(parientes)

            for p in parientes:
                # Para cada pariente...

                p_bd = conex_var_datos[p] if p in conex_var_datos else p
                if bd_datos is not None and p_bd not in bd_datos:
                    # Si tenemos datos y este variable pariente no existe, tendremos que buscar sus parientes también.

                    # ...pero si ya encontramos este variable en otra recursión, quiere decir que no tenemos
                    # suficientemente datos y que estamos andando en círculos.
                    if p in sn_dts:
                        raise RecursionError(
                            _('Estamos andando en círculos buscando variables con datos disponibles. Debes '
                              'especificar más datos. Puedes empezar con uno de estos variables: {}'
                              ).format(', '.join(sn_dts))
                        )

                    # Acordarse que ya intentamos buscar parientes con datos para este variable
                    sn_dts.add(p)

                    # Seguir con la recursión
                    _sacar_vars_recurs(v=p, c_v=c_v, sn_dts=sn_dts)

                if incluir_hermanos:
                    # Si incluyemos a los hermanos, agregarlos y sus parientes aquí.
                    hijos = d_vars[p]['hijos']
                    c_v.update(hijos)
                    for h in hijos:
                        if h not in c_v:
                            _sacar_vars_recurs(v=h, c_v=c_v, sn_dts=sn_dts)

            # Devolver el conjunto de variables asociados
            return c_v

        return _sacar_vars_recurs(var)


def _correr_modelo(x):
    """
    Función para inicializar y correr un modelo en paralelo.

    Parameters
    ----------
    x : tuple[Modelo, dict]
        Los parámetros. El primero es el modelo, el segundo el diccionario de parámetros para la simulación.

    Returns
    -------
    dict
        Los resultados de la simulación.
    """

    estado_mod, d_args = x

    mod = pickle.loads(estado_mod)

    # Después, simular el modelo y devolver los resultados, si hay.
    return mod.simular(**d_args)
