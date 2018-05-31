import os
import re
import shutil
from subprocess import run
from warnings import warn

import numpy as np

from tinamit import obt_val_config, _
from tinamit.BF import ModeloImpaciente
from .sahysmodIE import leer_info_dic_paráms, escribir_desde_dic_paráms


class ModeloSAHYSMOD(ModeloImpaciente):
    """

    """

    leng_orig = 'en'

    def __init__(símismo, datos_iniciales, exe_sahysmod=None):


        símismo.argsinic = (datos_iniciales, exe_sahysmod)

        # Find the SAHYSMOD executable path, if necessary.
        if exe_sahysmod is None:
            exe_sahysmod = obt_val_config('exe_sahysmod', mnsj=_('Especificar la ubicación de tu modelo (.exe) '
                                                                 'SAHYSMOD.'))
        símismo.SAHYSMOD_exe = exe_sahysmod

        # Number of (internal) polygons in the model
        símismo.n_polí = None

        # Empty dictionary to store input data later on
        símismo.dic_ingr = {}

        # Set the working directory to write model output, and remember where the initial data is stored.
        símismo.datos_inic = datos_iniciales
        símismo.direc_base = os.path.split(datos_iniciales)[0]

        # The path from which to read and write input and output data will be set later on according to the run name
        símismo.egreso = None  # type: str
        símismo.ingreso = None  # type: str
        símismo.direc_trabajo = None  # type: str

        # Prepare the command to the SAHYSMOD executable
        símismo.comanda = None

        # Inicialise as the parent class.
        super().__init__()

        # Set climatic variables. Actually, "variable" for the moment.
        símismo.conectar_var_clima(var='Pp - Rainfall', var_clima='Precipitación', combin='total',
                                conv=0.001)

    def _inic_dic_vars(símismo):

        símismo.variables.clear()

        for nombre, dic in vars_SAHYSMOD.items():
            símismo.variables[nombre] = {'val': None,
                                    'unidades': dic['unids'],
                                    'ingreso': dic['ingr'],
                                    'egreso': dic['egr'],
                                    'dims': (1,)  # Se cambiará después para variables espaciales
                                    }

        # Establecer los ingresos y egresos estacionales
        egresos_estacionales = [x for x in vars_egreso_SAHYSMOD if x[-1] == '#']

        ingresos_no_estacionales = [
            'Kr', 'CrA', 'CrB', 'CrU', 'Cr4', 'Hw', 'C1*', 'C2*', 'C3*', 'Cxf', 'Cxa', 'Cxb', 'Cqf'
        ]
        ingresos_estacionales = [x for x in vars_ingreso_SAHYSMOD if x[-1] == '#'
                                 and x[:-1] not in ingresos_no_estacionales]

        # Guardar todo al diccionario interno
        símismo.tipos_vars['Ingresos'] = [códs_a_vars[x] for x in vars_ingreso_SAHYSMOD]
        símismo.tipos_vars['Egresos'] = [códs_a_vars[x] for x in vars_egreso_SAHYSMOD]
        símismo.tipos_vars['IngrEstacionales'] = [códs_a_vars[x] for x in ingresos_estacionales]
        símismo.tipos_vars['EgrEstacionales'] = [códs_a_vars[x] for x in egresos_estacionales]

    def _iniciar_modelo(símismo, tiempo_final, nombre_corrida):

        # Crear un diccionario de trabajo específico a esta corrida.
        símismo.direc_trabajo = os.path.join(símismo.direc_base, '_temp', nombre_corrida)
        if os.path.isdir(símismo.direc_trabajo):
            shutil.rmtree(símismo.direc_trabajo)
        os.makedirs(símismo.direc_trabajo)
        símismo.egreso = os.path.join(símismo.direc_trabajo, 'SAHYSMOD.out')
        símismo.ingreso = os.path.join(símismo.direc_trabajo, 'SAHYSMOD.inp')

        # Generar la comanda de corrida (para después)
        args = dict(SAHYSMOD=símismo.SAHYSMOD_exe, ingreso=símismo.ingreso, egreso=símismo.egreso)
        símismo.comanda = '"{SAHYSMOD}" "{ingreso}" "{egreso}"'.format(**args)

        super().iniciar_modelo(tiempo_final=tiempo_final, nombre_corrida=nombre_corrida)

    def avanzar_modelo(símismo):

        # Limpiar archivos de egresos que podrían estar allí
        if os.path.isfile(símismo.egreso):
            os.remove(símismo.egreso)

        # Correr la comanda desde la línea de comanda
        run(símismo.comanda, cwd=símismo.direc_trabajo)

        # Verificar que SAHYSMOD generó egresos.
        if not os.path.isfile(símismo.egreso):
            raise FileNotFoundError(_('El modelo SAHYSMOD no genero egreso. Esto probablemente quiere decir que '
                                      'tuvo problema. ¡Diviértete! :)'))

    def cerrar_modelo(símismo):
        
        for f in os.listdir(símismo.direc_trabajo):
            if re.match('Name(0|[0-9]{2})$', f):
                os.remove(f)

    def escribir_archivo_ingr(símismo, n_años_simul, dic_ingr):

        # Establecer el número de años de simulación
        símismo.dic_ingr['NY'] = n_años_simul

        # Copiar datos desde el diccionario de ingresos
        for var, val in dic_ingr.items():
            var_cód = vars_SAHYSMOD[var]['cód']
            llave = var_cód.replace('#', '').upper()

            símismo.dic_ingr[llave] = val

        # Aseguarse que no quedamos con áreas que faltan
        for k in ["A", "B"]:
            vec = símismo.dic_ingr[k]
            vec[vec == -1] = 0

        # Y finalmente, escribir el archivo de valores de ingreso
        escribir_desde_dic_paráms(dic_paráms=símismo.dic_ingr, archivo_obj=símismo.ingreso)

    def leer_archivo_egr(símismo, n_años_egr):

        dic_egr = leer_arch_egr(archivo=símismo.egreso, n_est=símismo.n_estaciones, n_p=símismo.n_polí,
                                n_años=n_años_egr)

        for cr in ['CrA#', 'CrB#', 'CrU#', 'Cr4#', 'A#', 'B#', 'U#']:
            dic_egr[cr][dic_egr[cr] == -1] = 0

        # Ajustar la salinidad por la presencia de varios cultivos
        kr = dic_egr['Kr#']

        salin_suelo = np.zeros((símismo.n_estaciones, símismo.n_polí))

        # Crear una máscara boleana para cada valor potencial de Kr y llenarlo con la salinidad correspondiente
        kr0 = (kr == 0)
        salin_suelo[kr0] = dic_egr['A#'][kr0] * dic_egr['CrA#'][kr0] + \
                        dic_egr['B#'][kr0] * dic_egr['CrB#'][kr0] + \
                        dic_egr['U#'][kr0] * dic_egr['CrU#'][kr0]

        kr1 = (kr == 1)
        salin_suelo[kr1] = dic_egr['CrU#'][kr1] * dic_egr['U#'][kr1] + \
                        dic_egr['C1*#'][kr1] * (1 - dic_egr['U#'][kr1])

        kr2 = (kr == 2)
        salin_suelo[kr2] = dic_egr['CrA#'][kr2] * dic_egr['A#'][kr2] + \
                        dic_egr['C2*#'][kr2] * (1 - dic_egr['A#'][kr2])

        kr3 = (kr == 3)
        salin_suelo[kr3] = dic_egr['CrB#'][kr3] * dic_egr['B#'][kr3] + \
                        dic_egr['C3*#'][kr3] * (1 - dic_egr['B#'][kr3])

        kr4 = (kr == 4)
        salin_suelo[kr4] = dic_egr['Cr4#'][kr4]

        para_llenar = [{'mask': kr0, 'cr': ['Cr4#']},
                   {'mask': kr1, 'cr': ['CrA#', 'CrB#', 'Cr4#']},
                   {'mask': kr2, 'cr': ['CrB#', 'CrU#', 'Cr4#']},
                   {'mask': kr3, 'cr': ['CrA#', 'CrU#', 'Cr4#']},
                   {'mask': kr4, 'cr': ['CrA#', 'CrB#', 'CrU#']}
                   ]

        for d in para_llenar:
            l_cr = d['cr']
            mask = d['mask']

            for cr in l_cr:
                dic_egr[cr][mask] = salin_suelo[mask]

        # Convertir códigos de variables a nombres de variables
        dic_final = {códs_a_vars[c]: v for c, v in dic_egr.items()}

        # Devolver el diccionario final
        return dic_final

    def leer_archivo_vals_inic(símismo):

        # Leer el archivo de ingreso
        dic_ingr = leer_info_dic_paráms(archivo_fnt=símismo.datos_inic)
        símismo.dic_ingr.clear()
        símismo.dic_ingr.update(dic_ingr)  # Guardar valores para escribir el archivo de valores iniciales en el futuro

        # Guardar el número de estaciones y de polígonos
        símismo.n_estaciones = int(dic_ingr['NS'])
        símismo.dur_estaciones = [int(float(x)) for x in dic_ingr['TS']]  # La duración de las estaciones (en meses)
        símismo.n_polí = int(dic_ingr['NN_IN'])

        if dic_ingr['NY'] != 1:
            warn(_('Hay más que 1 año de simulación en el archivo de datos iniciales SAHYSMOD. Cambiamos '
                   'automáticamente a 1 año.'))
            dic_ingr['NY'] = 1

        # Asegurars que el número de estaciones es igual al número de duraciones de estaciones.
        if símismo.n_estaciones != len(símismo.dur_estaciones):
            raise ValueError(_('Error en el archivo de datos iniciales SAHYSMOD: el número de duraciones de estaciones'
                               'especificadas no corresponde al número de estaciones especificadas (líneas 3 y 4).'))

        # Formatear el diccionario final
        dic_final = {}
        for c in vars_ingreso_SAHYSMOD:
            llave = c.upper().replace('#', '')

            if llave in dic_ingr:
                var_name = códs_a_vars[c]
                dic_final[var_name] = dic_ingr[llave]

        return dic_final, (símismo.n_polí,)

    def paralelizable(símismo):
        """
        El modelo SAHYSMOD sí es paralelizable si las corridas tienen nombres distintos.

        :return: Verdadero.
        :rtype: bool
        """

        return True

    def __getinitargs__(símismo):
        return símismo.argsinic


# Un diccionario de variables SAHYSMOD. Ver la documentación SAHYSMOD para más detalles.
vars_SAHYSMOD = {'Pp - Rainfall': {'cód': 'Pp#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': False},
                 'Ci - Incoming canal salinity': {'cód': 'Ci#', 'unids': 'dS/m', 'ingr': True, 'egr': True},
                 'Cinf - Aquifer inflow salinity': {'cód': 'Cinf', 'unids': 'dS/m', 'ingr': True, 'egr': False},
                 'Dc - Capillary rise critical depth': {'cód': 'Dc', 'unids': 'm', 'ingr': True, 'egr': False},
                 'Dd - Subsurface drain depth': {'cód': 'Dd', 'unids': 'm', 'ingr': True, 'egr': False},
                 'Dr - Root zone thickness': {'cód': 'Dr', 'unids': 'm', 'ingr': True, 'egr': False},
                 'Dx - Transition zone thickness': {'cód': 'Dx', 'unids': 'm', 'ingr': True, 'egr': False},
                 'EpA - Potential ET crop A': {'cód': 'EpA#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': False},
                 'EpB - Potential ET crop B': {'cód': 'EpB#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': False},
                 'EpU - Potential ET non-irrigated': {'cód': 'EpU#', 'unids': 'm3/season/m2', 'ingr': True,
                                                      'egr': False},
                 'Flq - Aquifer leaching efficienty': {'cód': 'Flq', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Flr - Root zone leaching efficiency': {'cód': 'Flr', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Flx - Transition zone leaching efficiency': {'cód': 'Flx', 'unids': 'Dmnl', 'ingr': True,
                                                               'egr': False},
                 'Frd - Drainage function reduction factor': {'cód': 'Frd#', 'unids': 'Dmnl', 'ingr': True,
                                                              'egr': False},
                 'FsA - Water storage efficiency crop A': {'cód': 'FsA#', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'FsB - Water storage efficiency crop B': {'cód': 'FsB#', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'FsU - Water storage efficiency non-irrigated': {'cód': 'FsU#', 'unids': 'Dmnl',
                                                                  'ingr': True, 'egr': False},
                 'Fw - Fraction well water to irrigation': {'cód': 'Fw#', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Gu - Subsurface drainage for irrigation': {'cód': 'Gu#', 'unids': 'm3/season/m2',
                                                             'ingr': True, 'egr': False},
                 'Gw - Groundwater extraction': {'cód': 'Gw#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': True},
                 'Hp - Initial water level semi-confined': {'cód': 'Hc', 'unids': 'm', 'ingr': True, 'egr': False},
                 'IaA - Crop A field irrigation': {'cód': 'IaA#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': True},
                 'IaB - Crop B field irrigation': {'cód': 'IaB#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': True},
                 'Rice A - Crop A paddy?': {'cód': 'KcA#', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Rice B - Crop B paddy?': {'cód': 'KcB#', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Kd - Subsurface drainage?': {'cód': 'Kd', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Kf - Farmers\'s responses?': {'cód': 'Kf', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Kaq1 - Horizontal hydraulic conductivity 1': {'cód': 'Kaq1', 'unids': 'm/day', 'ingr': True,
                                                                'egr': False},
                 'Kaq2 - Horizontal hydraulic conductivity 2': {'cód': 'Kaq2', 'unids': 'm/day', 'ingr': True,
                                                                'egr': False},
                 'Kaq3 - Horizontal hydraulic conductivity 3': {'cód': 'Kaq3', 'unids': 'm/day', 'ingr': True,
                                                                'egr': False},
                 'Kaq4 - Horizontal hydraulic conductivity 4': {'cód': 'Kaq4', 'unids': 'm/day', 'ingr': True,
                                                                'egr': False},
                 'Ksc1 - Semi-confined aquifer 1?': {'cód': 'Ksc1', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Ksc2 - Semi-confined aquifer 2?': {'cód': 'Ksc2', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Ksc3 - Semi-confined aquifer 3?': {'cód': 'Ksc3', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Ksc4 - Semi-confined aquifer 4?': {'cód': 'Ksc4', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Kr - Land use key': {'cód': 'Kr#', 'unids': 'Dmnl', 'ingr': True, 'egr': True},
                 'Kvert - Vertical hydraulic conductivity semi-confined': {'cód': 'Kvert', 'unids': 'm/day',
                                                                           'ingr': True, 'egr': False},
                 'Lc - Canal percolation': {'cód': 'Lc#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': False},
                 'Peq - Aquifer effective porosity': {'cód': 'Peq', 'unids': 'm/m', 'ingr': True, 'egr': False},
                 'Per - Root zone effective porosity': {'cód': 'Per', 'unids': 'm/m', 'ingr': True, 'egr': False},
                 'Pex - Transition zone effective porosity': {'cód': 'Pex', 'unids': 'm/m', 'ingr': True, 'egr': False},
                 'Psq - Semi-confined aquifer storativity': {'cód': 'Psq', 'unids': 'Dmnl', 'ingr': True, 'egr': False},
                 'Ptq - Aquifer total pore space': {'cód': 'Ptq', 'unids': 'm/m', 'ingr': True, 'egr': False},
                 'Ptr - Root zone total pore space': {'cód': 'Ptr', 'unids': 'm/m', 'ingr': True, 'egr': False},
                 'Ptx - Transition zone total pore space': {'cód': 'Ptx', 'unids': 'm/m', 'ingr': True, 'egr': False},
                 'QH1 - Drain discharge to water table height ratio': {'cód': 'QH1', 'unids': 'm/day/m',
                                                                       'ingr': True, 'egr': False},
                 'QH2 - Drain discharge to sq. water table height ratio': {'cód': 'QH2', 'unids': 'm/day/m2',
                                                                           'ingr': True, 'egr': False},
                 'Qinf - Aquifer inflow': {'cód': 'Qinf', 'unids': 'm3/season/m2', 'ingr': True, 'egr': False},
                 'Qout - Aquifer outflow': {'cód': 'Qout', 'unids': 'm3/season/m2', 'ingr': True, 'egr': False},
                 'SL - Soil surface level': {'cód': 'SL', 'unids': 'm', 'ingr': True, 'egr': False},
                 'SiU - Surface inflow to non-irrigated': {'cód': 'SiU#', 'unids': 'm3/season/m2',
                                                           'ingr': True, 'egr': False},
                 'SdA - Surface outflow crop A': {'cód': 'SoA#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': False},
                 'SdB - Surface outflow crop B': {'cód': 'SoB#', 'unids': 'm3/season/m2', 'ingr': True, 'egr': False},
                 'SoU - Surface outflow non-irrigated': {'cód': 'SoU#', 'unids': 'm3/season/m2',
                                                         'ingr': True, 'egr': False},
                 'It - Total irrigation': {'cód': 'It#', 'unids': 'm3/season/m2', 'ingr': False, 'egr': True},
                 'Is - Canal irrigation': {'cód': 'Is#', 'unids': 'm3/season/m2', 'ingr': False, 'egr': True},

                 'FfA - Irrigation efficiency crop A': {'cód': 'FfA#', 'unids': 'Dmnl', 'ingr': False, 'egr': True},
                 'FfB - Irrigation efficiency crop B': {'cód': 'FfB#', 'unids': 'Dmnl', 'ingr': False, 'egr': True},
                 'FfT - Total irrigation efficiency': {'cód': 'FfT#', 'unids': 'Dmnl', 'ingr': False, 'egr': True},
                 'Io - Water leaving by canal': {'cód': 'Io#', 'unids': 'm3/season/m2', 'ingr': False, 'egr': True},
                 'JsA - Irrigation sufficiency crop A': {'cód': 'JsA#', 'unids': 'Dmnl', 'ingr': False, 'egr': True},
                 'JsB - Irrigation sufficiency crop B': {'cód': 'JsB#', 'unids': 'Dmnl', 'ingr': False, 'egr': True},
                 'EaU - Actual evapotranspiration nonirrigated': {'cód': 'EaU#', 'unids': 'm3/season/m2',
                                                                  'ingr': False, 'egr': True},
                 'LrA - Root zone percolation crop A': {'cód': 'LrA#', 'unids': 'm3/season/m2',
                                                        'ingr': False, 'egr': True},
                 'LrB - Root zone percolation crop B': {'cód': 'LrB#', 'unids': 'm3/season/m2',
                                                        'ingr': False, 'egr': True},
                 'LrU - Root zone percolation nonirrigated': {'cód': 'LrU#', 'unids': 'm3/season/m2',
                                                              'ingr': False, 'egr': True},
                 'LrT - Total root zone percolation': {'cód': 'LrT#', 'unids': 'm3/season/m2', 'ingr': False,
                                                       'egr': True},
                 'RrA - Capillary rise crop A': {'cód': 'RrA#', 'unids': 'm3/season/m2', 'ingr': False, 'egr': True},
                 'RrB - Capillary rise crop B': {'cód': 'RrB#', 'unids': 'm3/season/m2', 'ingr': False, 'egr': True},
                 'RrU - Capillary rise non-irrigated': {'cód': 'RrU#', 'unids': 'm3/season/m2', 'ingr': False,
                                                        'egr': True},
                 'RrT - Total capillary rise': {'cód': 'RrT#', 'unids': 'm3/season/m2', 'ingr': False, 'egr': True},
                 'Gti - Trans zone horizontal incoming groundwater': {'cód': 'Gti#', 'unids': 'm3/season/m2',
                                                                      'ingr': False, 'egr': True},
                 'Gto - Trans zone horizontal outgoing groundwater': {'cód': 'Gto#', 'unids': 'm3/season/m2',
                                                                      'ingr': False, 'egr': True},
                 'Qv - Net vertical water table recharge': {'cód': 'Qv#', 'unids': 'm', 'ingr': False, 'egr': True},
                 'Gqi - Aquifer horizontal incoming groundwater': {'cód': 'Gqi#', 'unids': 'm3/season/m2',
                                                                   'ingr': False, 'egr': True},
                 'Gqo - Aquifer horizontal outgoing groundwater': {'cód': 'Gqo#', 'unids': 'm3/season/m2',
                                                                   'ingr': False, 'egr': True},
                 'Gaq - Net aquifer horizontal flow': {'cód': 'Gaq#', 'unids': 'm3/season/m2',
                                                       'ingr': False, 'egr': True},
                 'Gnt - Net horizontal groundwater flow': {'cód': 'Gnt#', 'unids': 'm3/season/m2',
                                                           'ingr': False, 'egr': True},
                 'Gd - Total subsurface drainage': {'cód': 'Gd#', 'unids': 'm3/season/m2',
                                                    'ingr': False, 'egr': True},
                 'Ga - Subsurface drainage above drains': {'cód': 'Ga#', 'unids': 'm3/season/m2',
                                                           'ingr': False, 'egr': True},
                 'Gb - Subsurface drainage below drains': {'cód': 'Gb#', 'unids': 'm3/season/m2',
                                                           'ingr': False, 'egr': True},
                 'Dw - Groundwater depth': {'cód': 'Dw#', 'unids': 'm', 'ingr': False, 'egr': True},
                 'Hw - Water table elevation': {'cód': 'Hw#', 'unids': 'm', 'ingr': True, 'egr': True},
                 'Hq - Subsoil hydraulic head': {'cód': 'Hq#', 'unids': 'm', 'ingr': False, 'egr': True},
                 'Sto - Water table storage': {'cód': 'Sto#', 'unids': 'm', 'ingr': False, 'egr': True},
                 'Zs - Surface water salt': {'cód': 'Zs#', 'unids': 'm*dS/m', 'ingr': False, 'egr': True},
                 'Area A - Seasonal fraction area crop A': {'cód': 'A#', 'unids': 'Dmnl', 'ingr': True, 'egr': True},
                 'Area B - Seasonal fraction area crop B': {'cód': 'B#', 'unids': 'Dmnl', 'ingr': True, 'egr': True},
                 'Area U - Seasonal fraction area nonirrigated': {'cód': 'U#', 'unids': 'Dmnl', 'ingr': False,
                                                                  'egr': True},
                 'Uc - Fraction permanently non-irrigated': {'cód': 'Uc#', 'unids': 'Dmnl', 'ingr': False, 'egr': True},
                 'CrA - Root zone salinity crop A': {'cód': 'CrA#', 'unids': 'dS / m', 'ingr': True, 'egr': True},
                 'CrB - Root zone salinity crop B': {'cód': 'CrB#', 'unids': 'dS / m', 'ingr': True, 'egr': True},
                 'CrU - Root zone salinity non-irrigated': {'cód': 'CrU#', 'unids': 'dS / m',
                                                            'ingr': True, 'egr': True},
                 'Cr4 - Fully rotated land irrigated root zone salinity': {'cód': 'Cr4#', 'unids': 'dS / m',
                                                                           'ingr': False, 'egr': True},
                 'C1 - Key 1 non-permanently irrigated root zone salinity': {'cód': 'C1*#', 'unids': 'dS / m',
                                                                             'ingr': False, 'egr': True},
                 'C2 - Key 2 non-permanently irrigated root zone salinity': {'cód': 'C2*#', 'unids': 'dS / m',
                                                                             'ingr': False, 'egr': True},
                 'C3 - Key 3 non-permanently irrigated root zone salinity': {'cód': 'C3*#', 'unids': 'dS / m',
                                                                             'ingr': False, 'egr': True},
                 'Cxf - Transition zone salinity': {'cód': 'Cxf#', 'unids': 'dS / m', 'ingr': True, 'egr': True},
                 'Cxa - Transition zone above-drain salinity': {'cód': 'Cxa#', 'unids': 'dS / m', 'ingr': True,
                                                                'egr': True},
                 'Cxb - Transition zone below-drain salinity': {'cód': 'Cxb#', 'unids': 'dS / m', 'ingr': True,
                                                                'egr': True},
                 'Cti - Transition zone incoming salinity': {'cód': 'Cti#', 'unids': 'dS / m', 'ingr': False,
                                                             'egr': True},
                 'Cqf - Aquifer salinity': {'cód': 'Cqf#', 'unids': 'dS / m', 'ingr': True, 'egr': True},
                 'Cd - Drainage salinity': {'cód': 'Cd#', 'unids': 'ds / m', 'ingr': False, 'egr': True},
                 'Cw - Well water salinity': {'cód': 'Cw#', 'unids': 'ds / m', 'ingr': False, 'egr': True},
                 }

# Un diccionario para obtener el nombre de un variable a base de su código SAHYSMOD.
códs_a_vars = dict([(v['cód'], k) for (k, v) in vars_SAHYSMOD.items()])

# Una lista con únicamente los códigos de variables ingersos de SAHYSMOD
vars_ingreso_SAHYSMOD = [v['cód'] for v in vars_SAHYSMOD.values() if v['ingr']]

# Una lista con únicamente los códigos de variables egresos de SAHYSMOD
vars_egreso_SAHYSMOD = [v['cód'] for v in vars_SAHYSMOD.values() if v['egr']]


def leer_arch_egr(archivo, n_est, n_p, n_años):
    """
    :return: eje 0 = estación, eje 1 = polígono. -1 = valor que falta
    :rtype: dict[np.ndarray]
    """

    dic_datos = dict([(k, np.empty((n_est, n_p))) for k in vars_egreso_SAHYSMOD])
    for k, v in dic_datos.items():
        v[:] = -1

    with open(archivo, 'r') as d:
        l = ''
        while 'YEAR:      %i' % n_años not in l:
            l = d.readline()
        for est in range(n_est):
            for estación_polí in range(n_p):  # Leer el egreso de las estaciones del último año

                poly = []
                while re.match(' #', l) is None:
                    poly.append(l)
                    l = d.readline()

                l = d.readline()  # Avanzar una línea más para la próxima estación

                for cód in vars_egreso_SAHYSMOD:
                    var_out = cód.replace('#', '').replace('*', '\*')

                    for line in poly:

                        line += ' '
                        m = re.search(' %s += +([^ ]*)' % var_out, line)

                        if m:
                            val = m.groups()[0]
                            if val == '-':
                                val = -1
                            else:
                                try:
                                    val = float(val)
                                except ValueError:
                                    raise ValueError(
                                        _('El variable "{}" no se pudo leer del egreso SAHYSMOD').format(var_out)
                                    )
                            dic_datos[cód][(est, estación_polí)] = val
                            break
    return dic_datos