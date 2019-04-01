import csv
import ctypes
import os
import sys

from tinamit.config import _, obt_val_config
from tinamit.cositas import arch_más_recién


def gen_mod_vensim(archivo):
    if sys.platform[:3] != 'win':
        raise OSError(_('Desafortunadamente, el DLL de Vensim funciona únicamente en Windows.'))

    try:
        arch_dll_vensim = obt_val_config(['Vensim', 'dll'])
    except KeyError:
        arch_dll_vensim = None

    # Buscar el DLL de Vensim, si necesario.
    if arch_dll_vensim is None:
        probables = [
            'C:\\Windows\\System32\\vendll32.dll',
            'C:\\Windows\\SysWOW64\\vendll32.dll'
        ]
        arch_dll_vensim = next(a for a in probables if os.path.isfile(a))

    dll = ctypes.WinDLL(arch_dll_vensim)

    nmbr, ext = os.path.splitext(archivo)
    if ext == '.mdl':

        # Únicamente recrear el archivo .vpm si necesario
        if not os.path.isfile(nmbr + '.vpm') or arch_más_recién(archivo, nmbr + '.vpm'):
            publicar_modelo(mod=dll, archivo=archivo)
        archivo = nmbr + '.vpm'

    elif ext != '.vpm':
        raise ValueError(
            _('Vensim no sabe leer modelos del formato "{}". Debes darle un modelo ".mdl" o ".vpm".').format(ext)
        )

    # Inicializar Vensim
    cmd_vensim(func=dll.vensim_command,
               args=[''],
               mensaje_error=_('Error iniciando Vensim.'))

    # Cargar el modelo
    cmd_vensim(func=dll.vensim_command,
               args='SPECIAL>LOADMODEL|%s' % archivo,
               mensaje_error=_('Error cargando el modelo de Vensim.'))

    # Parámetros estéticos de ejecución.
    cmd_vensim(func=dll.vensim_be_quiet, args=[2],
               mensaje_error=_('Error en la comanda "vensim_be_quiet".'),
               val_error=-1)

    return dll


def verificar_vensim(símismo):
    """
    Esta función regresa el estatus de Vensim. Es particularmente útil para desboguear (no tiene uso en las
    otras funciones de esta clase, y se incluye como ayuda a la programadora.)

    :return: Código de estatus Vensim:
        | 0 = Vensim está listo
        | 1 = Vensim está en una simulación activa
        | 2 = Vensim está en una simulación, pero no está respondiendo
        | 3 = Malas noticias
        | 4 = Error de memoria
        | 5 = Vensim está en modo de juego
        | 6 = Memoria no libre. Llamar vensim_command() debería de arreglarlo.
        | 16 += ver documentación de Vensim para vensim_check_status() en la sección de DLL (Suplemento DSS)
    :rtype: int

    """

    # Obtener el estatus.
    estatus = cmd_vensim(func=símismo.mod.vensim_check_status,
                         args=[],
                         mensaje_error=_('Error verificando el estatus de Vensim. De verdad, la cosa '
                                         'te va muy mal.'),
                         val_error=-1)
    return int(estatus)


def publicar_modelo(mod, archivo):  # pragma: sin cobertura

    cmd_vensim(mod.vensim_command, 'SPECIAL>LOADMODEL|%s' % archivo)

    archivo_frm = os.path.join(os.path.split(os.path.dirname(__file__))[0], 'Vensim.frm')
    cmd_vensim(mod.vensim_command, ('FILE>PUBLISH|%s' % archivo_frm))


def obt_vars(mod):
    l_nombres = []
    for t in [1, 2, 4, 5, 12]:
        mem = ctypes.create_string_buffer(0)  # Crear una memoria intermedia

        # Verificar el tamaño necesario
        tamaño_nec = cmd_vensim(
            func=mod.vensim_get_varnames,
            args=['*', t, mem, 0],
            mensaje_error=_('Error obteniendo eñ tamaño de los variables Vensim.'),
            val_error=-1
        )

        mem = ctypes.create_string_buffer(tamaño_nec)  # Una memoria intermedia con el tamaño apropiado

        # Guardar y decodar los nombres de los variables.
        cmd_vensim(func=mod.vensim_get_varnames,
                   args=['*', t, mem, tamaño_nec],
                   mensaje_error=_('Error obteniendo los nombres de los variables de Vensim.'),
                   val_error=-1
                   )
        l_nombres += [
            x for x in mem.raw.decode().split('\x00')
            if x and x not in ['FINAL TIME', 'TIME STEP', 'INITIAL TIME', 'SAVEPER', 'Time']
        ]
    return l_nombres


def obt_editables(mod):
    # Para obtener los nombres de variables editables (se debe hacer así y no por `tipo_var` porque Vensim
    # los reporta como de tipo `Auxiliary`.
    mem = ctypes.create_string_buffer(0)  # Crear una memoria intermedia

    # Verificar el tamaño necesario
    tamaño_nec = cmd_vensim(
        func=mod.vensim_get_varnames,
        args=['*', 12, mem, 0],
        mensaje_error=_('Error obteniendo eñ tamaño de los variables Vensim.'),
        val_error=-1
    )

    mem = ctypes.create_string_buffer(tamaño_nec)  # Una memoria intermedia con el tamaño apropiado

    cmd_vensim(
        func=mod.vensim_get_varnames,
        args=['*', 12, mem, tamaño_nec],
        mensaje_error=_('Error obteniendo los nombres de los variables editables ("Gaming") de '
                        'VENSIM.'),
        val_error=-1
    )

    return [x for x in mem.raw.decode().split('\x00') if x]


def obt_unid_tiempo(mod):
    return obt_atrib_var(
        mod, var='TIME STEP', cód_attrib=1,
        mns_error=_('Error obteniendo la unidad de tiempo para el modelo Vensim.')
    )


def vdf_a_csv(mod, archivo_vdf=None, archivo_csv=None):

    if archivo_csv is None:
        archivo_csv = archivo_vdf

    # En Vensim, "!" quiere decir la corrida activa
    archivo_vdf = archivo_vdf or '!'
    archivo_csv = archivo_csv or '!'

    # Vensim hace la conversión para nosotr@s
    mod.vensim_command(
        'MENU>VDF2CSV|{archVDF}|{archCSV}'.format(
            archVDF=archivo_vdf + '.vdf', archCSV=archivo_csv + '.csv'
        ).encode()
    )

    # Re-aplicar la corrida activa
    if archivo_csv == '!':
        archivo_csv = corrida_activa

    # Leer el csv
    with open(archivo_csv + '.csv', 'r', encoding='UTF-8') as d:
        lect = csv.reader(d)

        # Cortar el último paso de simulación. Tinamït siempre corre simulaciones de Vensim para 1 paso adicional
        # para permitir que valores de variables conectados se puedan actualizar.
        # Para que quede claro: esto es por culpa de un error en Vensim, no es culpa nuestra.
        filas = [f[:-1] if len(f) > 2 else f for f in lect]

    # Hay que abrir el archivo de nuevo para re-escribir sobre el contenido existente-
    with open(archivo_csv + '.csv', 'w', encoding='UTF-8', newline='') as d:
        escr = csv.writer(d)
        escr.writerows(filas)


def cerrar_vensim(mod, paso):
    # Necesario para guardar los últimos valores de los variables conectados. (Muy incómodo, yo sé.)
    if paso != 1:
        cmd_vensim(func=mod.vensim_command,
                   args="GAME>GAMEINTERVAL|%i" % 1,
                   mensaje_error=_('Error estableciendo el paso de Vensim.'))
    cmd_vensim(func=mod.vensim_command,
               args="GAME>GAMEON",
               mensaje_error=_('Error terminando la simulación Vensim.'))

    # ¡Por fin! Llamar la comanda para terminar la simulación.
    cmd_vensim(func=mod.vensim_command,
               args="GAME>ENDGAME",
               mensaje_error=_('Error terminando la simulación Vensim.'))


def obt_atrib_var(mod, var, cód_attrib, mns_error=None):
    if cód_attrib in [4, 5, 6, 7, 8, 9, 10]:
        lista = True
    elif cód_attrib in [1, 2, 3, 11, 12, 13, 14]:
        lista = False
    else:
        raise ValueError(_('Código "{}" no reconocido para la comanda Vensim de obtener atributos de variables.')
                         .format(cód_attrib))

    if mns_error is None:
        l_atrs = [_('las unidades'), _('la descipción'), _('la ecuación'), _('las causas'), _('las consecuencias'),
                  _('la causas iniciales'), _('las causas activas'), _('los subscriptos'),
                  _('las combinaciones de subscriptos'), _('los subscriptos de gráfico'), _('el mínimo'),
                  _('el máximo'), _('el rango'), _('el tipo_mod')]
        mns_error1 = _('Error leyendo el tamaño de memoria para obtener {} del variable "{}" en Vensim') \
            .format(l_atrs[cód_attrib - 1], var)
        mns_error2 = _('Error leyendo {} del variable "{}" en Vensim.').format(l_atrs[cód_attrib - 1], var)
    else:
        mns_error1 = mns_error2 = mns_error

    mem = ctypes.create_string_buffer(10)
    tmñ = cmd_vensim(
        func=mod.vensim_get_varattrib,
        args=[var, cód_attrib, mem, 0],
        mensaje_error=mns_error1,
        val_error=-1,
    )

    mem = ctypes.create_string_buffer(tmñ)
    cmd_vensim(func=mod.vensim_get_varattrib,
               args=[var, cód_attrib, mem, tmñ],
               mensaje_error=mns_error2,
               val_error=-1)

    if lista:
        return [x for x in mem.raw.decode().split('\x00') if x]
    else:
        return mem.value.decode()


def cmd_vensim(func, args, mensaje_error=None, val_error=None):  # pragma: sin cobertura
    """
    Esta función sirve para llamar todo tipo_mod de comanda Vensim.

    Parameters
    ----------
    func: callable
        La función DLL a llamar.
    args: list | str
        Los argumento a pasar a la función. Si no hay, usar una lista vacía.
    mensaje_error: str
        El mensaje de error para mostrar si hay un error en la comanda.
    val_error: int
        Un valor de regreso Vensim que indica un error para esta función. Si se deja ``None``, todos
        valores que no son 1 se considerarán como erróneas.

    Returns
    -------
    int
        El código devuelto por Vensim.
    """

    # Asegurarse que args es una lista
    if type(args) is not list:
        args = [args]

    # Encodar en bytes todos los argumentos de texto.
    for n, a in enumerate(args):
        if type(a) is str:
            args[n] = a.encode()

    # Llamar la función Vensim y guardar el resultado.
    try:
        resultado = func(*args)
    except OSError:
        try:
            resultado = func(*args)
        except OSError as e:
            raise OSError(e)

    # Verificar su hubo un error.
    if val_error is None:
        error = (resultado != 1)
    else:
        error = (resultado == val_error)

    # Si hubo un error, avisar el usuario.
    if error:
        if mensaje_error is None:
            mensaje_error = _('Error con la comanda Vensim.')

        mensaje_error += _(' Código de error {}.').format(resultado)

        raise OSError(mensaje_error)

    # Devolver el valor devuelto por la función Vensim
    return resultado
