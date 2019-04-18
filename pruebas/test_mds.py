import os
import unittest

import numpy.testing as npt
import xarray.testing as xrt

from tinamit.envolt.mds import EnvolturaVensimDLL, EnvolturaPySDXMILE, EnvolturaPySDMDL, EnvolturaMDS, gen_mds, \
    ErrorNoInstalado

# Los tipos de modelos DS que queremos comprobar.
tipos_modelos = {
    'PySDVensim': {'envlt': EnvolturaPySDMDL, 'prueba': 'recursos/mds/prueba_senc.mdl'},
    'PySD_XMILE': {'envlt': EnvolturaPySDXMILE, 'prueba': 'recursos/mds/prueba_senc_xml.xmile'},
    'dllVensim': {'envlt': EnvolturaVensimDLL, 'prueba': 'recursos/mds/prueba_senc.vpm'}
}

# Agregar la ubicación del fuente actual
dir_act = os.path.split(__file__)[0]
for d_m in tipos_modelos.values():
    d_m['prueba'] = os.path.join(dir_act, d_m['prueba'])


def generar_modelos_prueba():
    mods = {}
    for nmb, dic in tipos_modelos.items():
        cls = dic['envlt']
        if cls.instalado():
            mods[nmb] = cls(dic['prueba'])

    return mods


class TestLeerModelos(unittest.TestCase):
    """
    Verifica el funcionamiento de los programas de mds.
    """

    @classmethod
    def setUpClass(cls):

        # Generar las instancias de los modelos
        cls.modelos = generar_modelos_prueba()

        # Información sobre los variables del modelo de prueba
        cls.info_vars = {
            'Lluvia': {'unidades': 'm3/mes', 'líms': (0, None)},
            'Nivel lago inicial': {'unidades': 'm3', 'líms': (0, None)},
            'Flujo río': {'unidades': 'm3/mes', 'líms': (0, None)},
            'Lago': {'unidades': 'm3', 'líms': (0, None)},
            'Evaporación': {'unidades': 'm3/mes', 'líms': (0, None)},
            'Aleatorio': {'unidades': 'Sdmn', 'líms': (0, 1)},
        }

    def test_leer_vars(símismo):
        """
        Comprobar que los nombres de los variables se leyeron correctamente.
        """
        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                vars_modelo = {str(vr) for vr in mod.variables}
                símismo.assertSetEqual(set(símismo.info_vars), vars_modelo)

    def test_unid_tiempo(símismo):
        """
        Comprobar que las unidades de tiempo se leyeron correctamente.
        """
        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                símismo.assertEqual('mes', mod.unidad_tiempo())

    def test_leer_info(símismo):
        """
        Comprobar que la documentación de cada variable se leyó correctamente.
        """

        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                símismo.assertTrue(len(mod.variables[v].info) > 0 for v in mod.variables)

    def test_leer_unidades(símismo):
        """
        Comprobar que las unidades de los variables se leyeron correctamente.
        """

        unids = {v: d_v['unidades'].lower() for v, d_v in símismo.info_vars.items()}

        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                unids_mod = {str(v): mod.variables[v].unid.lower() for v in mod.variables}
                símismo.assertDictEqual(unids, unids_mod)

    def test_leer_líms(símismo):
        """
        Comprobar que los límites de los variables se leyeron correctamente.
        """

        unids = {v: d_v['líms'] for v, d_v in símismo.info_vars.items()}

        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                unids_mod = {str(v): mod.variables[v].líms for v in mod.variables}
                símismo.assertDictEqual(unids, unids_mod)

    @classmethod
    def tearDownClass(cls):
        """
        Limpiar todos los archivos temporarios.
        """

        limpiar_mds()


class TestSimular(unittest.TestCase):
    @classmethod
    def setUpClass(cls):

        # Generar las instancias de los modelos
        cls.modelos = generar_modelos_prueba()
        cls.vals_inic = cls.info_vars = {
            'Nivel lago inicial': 1450,
            'Aleatorio': 2.3,
        }
        # Para cada modelo...
        for mod in cls.modelos.values():
            # Los variables iniciales

            # Correr el modelo para 200 pasos, guardando los egresos del variable "Lago"
            mod.simular(t=200, vals_extern=cls.vals_inic, vars_interés=['Lago', 'Aleatorio', 'Nivel lago inicial'])

    def test_cmb_vals_inic_constante_en_resultados(símismo):
        """
        Comprobar que los valores iniciales se establecieron correctamente en los resultados.
        """

        for ll, mod in símismo.modelos.items():
            v = 'Nivel lago inicial'
            d_v = símismo.info_vars[v]

            with símismo.subTest(mod=ll):
                npt.assert_array_equal(mod.leer_resultados(v)[v], d_v['val_inic'])

    def test_cambiar_vals_inic_var_dinámico(símismo):
        """
        Asegurarse que los valores iniciales de variables dinámicos aparezcan en el paso 0 de los resultados.
        """

        for ll, mod in símismo.modelos.items():
            v = 'Aleatorio'
            d_v = símismo.info_vars[v]

            with símismo.subTest(mod=ll):
                símismo.assertEqual(mod.leer_resultados(v)[v][0], d_v['val_inic'])

    def test_cambiar_vals_inic_nivel(símismo):
        """
        Comprobar que valores iniciales pasados a un variable de valor inicial aparezcan en los resultados también.
        """
        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                símismo.assertEqual(
                    mod.leer_resultados('Lago')['Lago'].values[0],
                    símismo.info_vars['Nivel lago inicial']['val_inic']
                )

    def test_resultados_simul(símismo):
        """
        Assegurarse que la simulación dió los resultados esperados.
        """

        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                # Leer el resultado del último día de simulación pára el variable "Lago"
                val_simulado = mod.leer_resultados('Lago')['Lago'].values[-1]

                # Debería ser aproximativamente igual a 100
                símismo.assertEqual(round(val_simulado, 3), 100)

    def test_escribir_leer_arch_resultados(símismo):
        for ll, mod in símismo.modelos.items():
            for frmt in ['.json', '.csv']:
                with símismo.subTest(mod=ll, frmt=frmt):
                    arch = ll + '_prb'
                    mod.guardar_resultados(nombre=arch, frmt=frmt)
                    leídos = EnvolturaMDS.leer_arch_resultados(archivo=arch, var='Lago')
                    refs = mod.leer_resultados('Lago')
                    xrt.assert_identical(leídos, refs)
                    os.remove(arch + frmt)

    def test_leer_resultados_vdf_vensim(símismo):

        if 'dllVensim' in símismo.modelos:
            mod = símismo.modelos['dllVensim']
            leídos = mod.leer_arch_resultados(archivo=mod.corrida_activa + '.vdf', var='Lago')
            refs = mod.leer_resultados(var='Lago')
            xrt.assert_allclose(leídos, refs, rtol=1e-3)

    @classmethod
    def tearDownClass(cls):
        """
        Limpiar todos los archivos temporarios.
        """

        limpiar_mds()


class Test_OpcionesSimul(unittest.TestCase):
    """
    Verifica el funcionamiento de las simulaciones de de mds.
    """

    @classmethod
    def setUpClass(cls):

        # Generar las instancias de los modelos
        cls.modelos = generar_modelos_prueba()

    def test_simul_con_paso_2(símismo):
        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                res_paso_2 = mod.simular(t_final=100, paso=2, vars_interés=['Lago'])['Lago']
                res_paso_1 = mod.simular(t_final=100, paso=1, vars_interés=['Lago'])['Lago'][::2]
                npt.assert_array_equal(res_paso_1, res_paso_2)

    def test_simul_con_paso_inválido(símismo):
        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                with símismo.assertRaises(ValueError):
                    mod.simular(t_final=100, paso=0)

    def test_simul_exprés(símismo):
        for ll, mod in símismo.modelos.items():
            with símismo.subTest(mod=ll):
                mod.combin_pasos = False
                res_por_paso = mod.simular(t_final=100, paso=1, vars_interés=['Lago'])['Lago']
                mod.combin_pasos = True
                res_exprés = mod.simular(t_final=100, paso=1, vars_interés=['Lago'])['Lago']
                npt.assert_allclose(res_por_paso, res_exprés, 1e-3)


class TestGenerarMDS(unittest.TestCase):
    """
    Verifica el funcionamiento del generado automático de modelos DS.
    """

    def test_generación_auto_mds(símismo):
        """
        Verificamos que funcione la generación automática de modelos DS a base de un fuente.
        """

        for m, d in tipos_modelos.items():
            with símismo.subTest(ext=os.path.splitext(d['prueba'])[1], envlt=d['envlt'].__name__):
                try:
                    mod = gen_mds(d['prueba'])  # Generar el modelo
                    símismo.assertIsInstance(mod, EnvolturaMDS)
                except ErrorNoInstalado:
                    # No hay problema si el mds no se pudo leer en la computadora actual. De pronto no estaba instalado.
                    pass

    def test_error_extensión(símismo):
        """
        Comprobar que extensiones no reconocidas devuelvan un error.
        """

        with símismo.assertRaises(ErrorNoInstalado):
            gen_mds('recursos/mds/Modelo con extensión no reconocida.வணக்கம்')

    def test_modelo_erróneo(símismo):
        """
        Asegurarse que un fuente erróneo devuelva un error.
        """

        with símismo.assertRaises(FileNotFoundError):
            gen_mds('Yo no existo.mdl')


def limpiar_mds(direc='./recursos/mds'):
    """
    Limpiamos todos los documentos temporarios generados por los programas de modelos DS.
    """
    for c in os.walk(direc):
        for a in c[2]:
            ext = os.path.splitext(a)[1]
            try:
                if ext in ['.2mdl', '.vdf', '.py', '.csv']:
                    os.remove(os.path.join(direc, a))
            except (FileNotFoundError, PermissionError):
                pass
