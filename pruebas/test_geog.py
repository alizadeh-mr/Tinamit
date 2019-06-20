import os
import random
import shutil
import tempfile
import unittest

import numpy as np
from pruebas.recursos.mod.prueba_mod import ModeloPrueba
from tinamit.geog.mapa import dibujar_mapa, dibujar_mapa_de_res, \
    Calle, Ciudad, Bosque, OtraForma, Agua, \
    FormaDinámicaNumérica, FormaDinámicaNombrada
from tinamit.geog.región import Nivel, Lugar, gen_lugares
from tinamit.mod import OpsSimulGrupo

dir_act = os.path.split(__file__)[0]
arch_csv_geog = os.path.join(dir_act, 'recursos/datos/prueba_geog.csv')
arch_frm_nombrada = os.path.join(dir_act, 'recursos/frm/munis.shp')
arch_frm_numérica = os.path.join(dir_act, 'recursos/frm/frm_numérica.shp')
arch_frm_otra = os.path.join(dir_act, 'recursos/frm/otra_frm.shp')

arch_clim_diario = os.path.join(dir_act, 'recursos/datos/clim_diario.csv')
arch_clim_mensual = os.path.join(dir_act, 'recursos/datos/clim_mensual.csv')
arch_clim_anual = os.path.join(dir_act, 'recursos/datos/clim_anual.csv')


class TestRegión(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        muni = Nivel('Municipio')
        dept = Nivel('Departamento', subniveles=muni)
        terr = Nivel('Territorio', subniveles=muni)
        país = Nivel('País', subniveles=[dept, terr])
        muni1, muni2, muni3 = [Lugar('Muni%i' % i, nivel=muni, cód='M' + str(i)) for i in range(1, 4)]

        dept1 = Lugar('Dept1', nivel=dept, cód='D1', sub_lugares=[muni1, muni2])
        dept2 = Lugar('Dept2', nivel=dept, cód='D2', sub_lugares=[muni3])
        terr1 = Lugar('Terr1', nivel=terr, cód='T1', sub_lugares=[muni1])
        terr2 = Lugar('Terr2', nivel=terr, cód='T2', sub_lugares=[muni2])
        cls.guate = Lugar(
            'Guatemala', sub_lugares={muni1, muni2, muni3, dept1, dept2, terr1, terr2},
            nivel=país
        )

        cls.munis = {'1': muni1, '2': muni2, '3': muni3}
        cls.depts = {'1': dept1, '2': dept2}
        cls.terrs = {'1': terr1, '2': terr2}

    def test_obt_lugares(símismo):
        símismo.assertSetEqual(
            símismo.guate.lugares(),
            {símismo.guate, *símismo.munis.values(), *símismo.depts.values(), *símismo.terrs.values()}
        )

    def test_obt_lugares_con_nivel(símismo):
        símismo.assertSetEqual(símismo.guate.lugares(nivel='Municipio'), set(símismo.munis.values()))

    def test_obt_lugares_en(símismo):
        símismo.assertSetEqual(
            símismo.guate.lugares(en='D1', nivel='Municipio'),
            símismo.depts['1'].sub_lugares
        )

    def test_obt_lugares_donde_no_hay(símismo):
        símismo.assertSetEqual(
            símismo.guate.lugares(en='D1', nivel='Territorio'),
            set()
        )

    def test_buscar_de_código(símismo):
        símismo.assertEqual(símismo.guate['M1'], símismo.munis['1'])

    def test_buscar_de_nombre(símismo):
        símismo.assertEqual(símismo.guate.buscar_nombre('Muni1'), símismo.munis['1'])

    def test_buscar_código_no_existe(símismo):
        with símismo.assertRaises(ValueError):
            símismo.guate.buscar_nombre('Hola, yo no existo.')


class TestGenAuto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lugar = gen_lugares(arch_csv_geog, nivel_base='País', nombre='Iximulew')

    def test_niveles(símismo):
        nivel = símismo.lugar.nivel
        símismo.assertEqual(nivel, 'País')
        símismo.assertSetEqual(set(str(n) for n in nivel.subniveles), {'Departamento', 'Territorio'})
        símismo.assertEqual(nivel['Departamento'].subniveles, 'Municipio')

    def test_lugares(símismo):
        símismo.assertEqual(símismo.lugar.buscar_nombre('SOLOLÁ', 'Departamento').cód, '7')
        símismo.assertEqual(símismo.lugar.buscar_nombre('SOLOLÁ', 'Municipio').cód, '701')


class TestMapa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir_ = tempfile.mkdtemp(prefix='prb_mapa_')

    def _verificar_dibujó(símismo, formas, nombre):
        arch = os.path.join(símismo.dir_, nombre)
        dibujar_mapa(formas, arch)
        símismo.assertTrue(os.path.isfile(arch))
        os.remove(arch)

    def test_dibujar_formas_estáticas(símismo):
        frms = [cls(arch_frm_otra) for cls in [Calle, Ciudad, Bosque, OtraForma, Agua]]
        símismo._verificar_dibujó(frms, 'mapa_estático.jpeg')

    def test_dibujar_forma_numérica(símismo):
        frm = FormaDinámicaNumérica(arch_frm_numérica, col_id='Id')
        frm.estab_valores(np.random.rand(*frm.valores.shape))
        símismo._verificar_dibujó(frm, 'mapa_matriz.jpeg')

    def test_dibujar_forma_numérica_sin_id(símismo):
        frm = FormaDinámicaNumérica(arch_frm_numérica)
        frm.estab_valores(np.random.rand(*frm.valores.shape))
        símismo._verificar_dibujó(frm, 'mapa_matriz_sin_id.jpeg')

    def test_dibujar_forma_nombrada(símismo):
        frm = FormaDinámicaNombrada(arch_frm_nombrada, col_id='COD_MUNI')
        frm.estab_valores({id_: random.random() for id_ in frm.ids})
        símismo._verificar_dibujó(frm, 'mapa_dict.jpeg')

    def test_dibujar_escala_valores(símismo):
        frm = FormaDinámicaNumérica(arch_frm_numérica, col_id='Id')
        frm.estab_valores(np.random.rand(*frm.valores.shape), escala_valores=(0, 2))
        símismo._verificar_dibujó(frm, 'mapa_escala.jpeg')

    def test_dibujar_unidades(símismo):
        frm = FormaDinámicaNumérica(arch_frm_numérica, col_id='Id')
        frm.estab_valores(np.random.rand(*frm.valores.shape), unidades='Cosos')
        símismo._verificar_dibujó(frm, 'mapa_unids.jpeg')

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir_)


class TestMapaResultados(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.dir_ = tempfile.mkdtemp(prefix='prb_mapa_res_')

    def test_mapa_de_simul(símismo):
        frm = FormaDinámicaNumérica(arch_frm_numérica, col_id='Id')
        extern = {'Vacío': np.arange(len(frm.ids))}
        res = ModeloPrueba(dims=(215,)).simular(t=10, vals_extern=extern)
        dibujar_mapa_de_res(forma_dinámica=frm, res=res, var='Vacío', t=3, directorio=símismo.dir_)

    def test_mapa_de_simul_grupo(símismo):
        ops = OpsSimulGrupo(t=3, vals_extern=[{'Vacío': 1}, {'Vacío': 3}], nombre=['701', '101'])
        res = ModeloPrueba().simular_grupo(ops)

        frm = FormaDinámicaNombrada(arch_frm_nombrada, col_id='COD_MUNI')
        dibujar_mapa_de_res(forma_dinámica=frm, res=res, var='Vacío', t=3, directorio=símismo.dir_)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.dir_)
