"""Solicitudes de ejemplo redactadas por el equipo para entrenar el clasificador (S4-11).

Cada línea de `_TEXTO` es un ejemplo con el formato `categoría | urgencia | impacto | texto`:

- categoría: Hardware, Software, Redes o Cuentas y accesos.
- urgencia: 1 a 3 (3 = hay que atenderla ya). Ver `ml/README.md`.
- impacto: 1 a 3 (3 = afecta a muchas personas o a un servicio general).
- texto: cómo lo escribiría una persona al registrar la solicitud.

Las líneas vacías y las que empiezan con `#` se ignoran. Para agregar ejemplos, añade
líneas y vuelve a generar el conjunto de datos con `python -m ml.etl.build_dataset`.
Cada categoría debe tener la misma cantidad de ejemplos (el script avisa si no).
"""

_TEXTO = """
# Hardware
Hardware | 3 | 3 | Se apagaron todos los equipos del laboratorio de cómputo 3 al mismo tiempo y hay un examen en curso.
Hardware | 3 | 2 | El proyector del aula B-204 no enciende y la clase de las 11:00 ya empezó con 30 alumnos.
Hardware | 3 | 1 | Mi computadora no arranca y tengo que entregar hoy el reporte al subdirector; solo muestra pantalla negra.
Hardware | 2 | 1 | El teclado de mi equipo tiene varias teclas que no responden, puedo trabajar con uno externo prestado.
Hardware | 1 | 1 | Se me despegó una pata de goma del mouse, no es urgente pero lo reporto.
Hardware | 2 | 2 | La impresora de la coordinación atasca el papel cada vez que imprimimos y somos seis personas que la usamos.
Hardware | 1 | 2 | Dos monitores del cubículo de profesores tienen manchas en la pantalla, se ve pero se puede trabajar.
Hardware | 2 | 3 | Varias computadoras del laboratorio 2 se reinician solas cada pocos minutos, afecta a los grupos de la tarde.
Hardware | 1 | 3 | Las bocinas de todas las aulas del edificio C tienen ruido de fondo; no impide dar clase pero es molesto.
Hardware | 3 | 2 | Las dos computadoras de la oficina de posgrado se apagaron con olor a quemado y ahí están los expedientes de hoy.
Hardware | 2 | 1 | La batería de mi laptop institucional dura solo 20 minutos, necesito trabajar conectada.
Hardware | 1 | 1 | Quiero solicitar un cambio de mouse inalámbrico porque el actual es muy pequeño para mi mano.
Hardware | 3 | 1 | Se rompió el conector del cargador de mi laptop, me quedo sin batería en una hora y tengo videollamada.
Hardware | 2 | 2 | El escáner de la oficina de control escolar no es reconocido por ninguna computadora desde ayer.
Hardware | 1 | 2 | Sería bueno reponer los cables HDMI de tres aulas del edificio A, hoy los docentes comparten uno.
Hardware | 3 | 3 | El proyector de la sala de usos múltiples falla justo antes del evento de bienvenida con 200 asistentes.
Hardware | 2 | 1 | La cámara web de mi computadora no se detecta y la necesito para mis asesorías virtuales de la semana.
Hardware | 1 | 1 | El monitor de mi escritorio se ve un poco amarillento, quisiera que lo revisen cuando puedan.
Hardware | 2 | 3 | El aire acondicionado del cuarto de comunicaciones hace mucho ruido y la temperatura va subiendo.
Hardware | 3 | 2 | Las dos computadoras de la ventanilla de atención a alumnos no encienden y hay fila de gente esperando.
Hardware | 2 | 2 | El pizarrón interactivo del aula 105 no responde al tacto, usamos plumón mientras tanto.
Hardware | 1 | 1 | Pido revisar el ventilador de mi equipo, hace un zumbido leve pero todo funciona normal.
Hardware | 3 | 1 | Se derramó café sobre el teclado de mi laptop y ya no enciende, tengo calificaciones por capturar hoy.
Hardware | 2 | 3 | Los discos duros de las computadoras del laboratorio de diseño están casi llenos y los programas van muy lentos.
Hardware | 1 | 2 | El mouse de la computadora compartida de la sala de profesores se atora de vez en cuando.
Hardware | 2 | 1 | Mi disco duro externo institucional no es reconocido y ahí guardo los materiales de la semana.
Hardware | 3 | 3 | Se fue la energía en el laboratorio de redes y los equipos no encienden aunque regresó la luz; hay prácticas programadas.
Hardware | 1 | 2 | Las etiquetas de inventario de los equipos del laboratorio 4 están ilegibles, conviene reponerlas.
Hardware | 2 | 2 | Las computadoras de la biblioteca digital tardan más de cinco minutos en iniciar, afecta a quienes consultan por turnos.
Hardware | 3 | 2 | El no-break de la oficina del DTIC suena con alarma continua y los equipos se están apagando.

# Software
Software | 3 | 3 | La plataforma de aulas virtuales no carga para nadie y hoy cierran las entregas de los proyectos finales.
Software | 3 | 2 | El sistema de control escolar marca error al capturar calificaciones y la fecha límite de actas es hoy a las 15:00.
Software | 3 | 1 | Excel se cierra solo cada vez que abro el archivo de nómina y debo enviarlo hoy a recursos humanos.
Software | 2 | 1 | Mi navegador muestra cada rato un aviso de actualización que interrumpe mi trabajo, pero puedo seguir.
Software | 1 | 1 | Me gustaría que instalen un tema oscuro en el editor de texto de mi computadora, es solo preferencia.
Software | 2 | 2 | El software de simulación de circuitos marca licencia vencida en los equipos del laboratorio de electrónica, la práctica es la próxima semana.
Software | 1 | 2 | La versión de Python de las computadoras del laboratorio 1 es antigua, ojalá la actualicen antes del próximo semestre.
Software | 2 | 3 | Después de la actualización de anoche, el antivirus de las computadoras administrativas vuelve muy lento todo el sistema.
Software | 1 | 3 | El portal institucional muestra algunos textos con acentos mal codificados en varias secciones, aunque se entiende.
Software | 3 | 2 | En el departamento de finanzas no abre la aplicación de pagos y hoy se depositan los honorarios del personal.
Software | 2 | 1 | AutoCAD se congela al guardar archivos grandes y he perdido avances dos veces esta semana.
Software | 1 | 1 | Solicito instalar la aplicación para editar PDF en mi computadora cuando haya oportunidad.
Software | 3 | 1 | Teams no me deja entrar a la reunión de tesis que empieza en diez minutos, dice que mi versión no es compatible.
Software | 2 | 2 | El programa de captura del servicio social no guarda los datos de los alumnos de mi grupo desde el lunes.
Software | 1 | 2 | El lector de PDF de la sala de profesores abre los archivos con una fuente extraña, aunque se pueden leer.
Software | 3 | 3 | El sistema de inscripciones en línea no responde y miles de alumnos intentan reinscribirse hoy, último día.
Software | 2 | 1 | MATLAB me pide activar la licencia cada vez que lo abro y pierdo tiempo antes de cada clase.
Software | 1 | 1 | Quisiera que el reloj de mi computadora muestre el formato de 24 horas, sin prisa.
Software | 2 | 3 | La biblioteca digital muestra errores intermitentes al descargar artículos para todos los alumnos de posgrado.
Software | 3 | 2 | El sistema de reservación de salas falla y hay tres reuniones de academia por comenzar sin sala asignada.
Software | 2 | 2 | El software del laboratorio de química no abre en dos de las computadoras que usamos para las prácticas de mañana.
Software | 1 | 3 | Hay un error de ortografía en el mensaje de bienvenida del portal de servicios, lo vemos todos los usuarios.
Software | 3 | 1 | El correo en el navegador no me deja adjuntar el acta firmada y debo enviarla a la coordinación en 30 minutos.
Software | 2 | 3 | La aplicación de asistencia con código QR se traba en todos los salones durante la primera hora de clases.
Software | 1 | 1 | No sé cómo cambiar el idioma de la interfaz de mi programa de diseño, ¿me pueden orientar?
Software | 2 | 2 | Las computadoras del aula 202 tienen instaladas dos versiones distintas del compilador y los alumnos se confunden.
Software | 3 | 3 | Un virus bloqueó los archivos de varias computadoras del edificio administrativo y aparece un mensaje pidiendo dinero.
Software | 1 | 2 | Pido que se agregue la opción de exportar a CSV en el reporte de solicitudes cuando sea posible.
Software | 2 | 2 | La hoja de cálculo compartida de horarios tarda en abrir y a veces no guarda los cambios de nadie.
Software | 3 | 2 | El sistema de evaluación docente se cae cada vez que lo intentamos usar y el periodo de captura cierra hoy.

# Redes
Redes | 3 | 3 | No hay internet en todo el edificio de ingeniería desde hace una hora y se están aplicando exámenes en línea.
Redes | 3 | 2 | La red inalámbrica del aula magna no conecta y la conferencia con invitados externos empieza en 20 minutos.
Redes | 3 | 1 | Mi computadora no obtiene dirección IP y debo conectarme ya a la defensa de tesis virtual.
Redes | 2 | 1 | El Wi-Fi de mi cubículo se corta cada pocos minutos, puedo trabajar usando datos de mi celular.
Redes | 1 | 1 | Quisiera saber cuál es el nombre de la red para visitantes, no tengo prisa.
Redes | 2 | 2 | El internet del laboratorio de cómputo 2 está muy lento desde la mañana y los alumnos no pueden descargar sus prácticas.
Redes | 1 | 2 | En la sala de maestros la señal inalámbrica es débil solo en una esquina, pero funciona.
Redes | 2 | 3 | Las videollamadas se cortan constantemente en todos los pisos del edificio B desde el lunes.
Redes | 1 | 3 | El portal cautivo de la red de alumnos muestra el logotipo viejo de la facultad, aunque conecta bien.
Redes | 3 | 2 | Se cayó la red en el departamento de servicios escolares y no podemos atender trámites con los alumnos formados.
Redes | 2 | 1 | La VPN me desconecta a cada rato cuando trabajo desde casa y pierdo mis sesiones remotas.
Redes | 1 | 1 | Pido que me habiliten acceso a la red inalámbrica en mi segundo dispositivo cuando puedan.
Redes | 3 | 1 | No puedo entrar por VPN al servidor de la tesis y mi revisión es hoy en una hora.
Redes | 2 | 2 | El puerto de red de la oficina de la coordinación no da conexión a los dos equipos conectados a él.
Redes | 1 | 2 | El cable de red del cubículo de investigación está muy tirante y conviene reacomodarlo.
Redes | 3 | 3 | El conmutador principal del edificio A dejó de funcionar y toda la facultad está sin red y sin telefonía IP.
Redes | 2 | 1 | Mi impresora de red ya no aparece en mi computadora, aunque el resto de equipos sí la ven.
Redes | 1 | 1 | Me gustaría que la contraseña del Wi-Fi del taller sea más fácil de recordar.
Redes | 2 | 3 | La red de los laboratorios de cómputo pierde conexión a internet cada media hora y afecta todas las clases de la tarde.
Redes | 3 | 2 | El enlace de la biblioteca está caído y no se pueden prestar libros, hay alumnos con fecha de devolución hoy.
Redes | 2 | 2 | Nadie en el piso 2 del edificio de posgrado puede acceder a las carpetas compartidas desde ayer.
Redes | 1 | 3 | La señal del Wi-Fi en el patio central es débil, ojalá se pueda mejorar para los estudiantes.
Redes | 3 | 1 | Mi equipo muestra «sin acceso a internet» justo cuando estoy por empezar mi clase en línea.
Redes | 2 | 3 | Los puntos de acceso inalámbrico del edificio C se reinician solos varias veces al día.
Redes | 1 | 1 | Quiero conocer la velocidad contratada de internet en mi cubículo, es solo curiosidad técnica.
Redes | 2 | 2 | El teléfono IP de la oficina de la dirección no tiene tono y solo lo usamos para llamadas internas importantes.
Redes | 3 | 3 | Un corte de fibra dejó sin conexión a toda la facultad, incluidas aulas con evaluaciones en línea.
Redes | 1 | 2 | Se solicita ordenar el cableado del gabinete del laboratorio 3, está desordenado pero todo funciona.
Redes | 2 | 1 | Mi laptop se conecta al Wi-Fi pero las páginas institucionales no cargan, otras sí.
Redes | 3 | 2 | El Wi-Fi de la sala de juntas está caído y en media hora llegan los evaluadores de acreditación.

# Cuentas y accesos
Cuentas y accesos | 3 | 1 | Mi cuenta institucional está bloqueada y tengo que subir calificaciones antes de las 14:00.
Cuentas y accesos | 2 | 1 | Olvidé mi contraseña del correo institucional y no recibo el mensaje de recuperación.
Cuentas y accesos | 1 | 1 | Quisiera cambiar el nombre que aparece en mi correo institucional, no es urgente.
Cuentas y accesos | 3 | 3 | Nadie puede iniciar sesión en la plataforma de aulas virtuales y hay exámenes programados ahora.
Cuentas y accesos | 2 | 2 | Los cinco becarios nuevos del laboratorio aún no tienen cuenta y no pueden usar los equipos.
Cuentas y accesos | 1 | 2 | A los profesores de tiempo parcial les aparece su nombre incompleto en el directorio, aunque pueden entrar.
Cuentas y accesos | 3 | 2 | Se bloqueó el acceso de todo el personal de servicios escolares al sistema y hay trámites en ventanilla.
Cuentas y accesos | 2 | 3 | El inicio de sesión único falla de forma intermitente para muchos alumnos de la facultad.
Cuentas y accesos | 1 | 3 | El correo de bienvenida a los alumnos nuevos llega con un enlace al manual viejo.
Cuentas y accesos | 3 | 1 | Mi usuario fue desactivado por error y debo registrar el acta final del grupo hoy.
Cuentas y accesos | 2 | 1 | No me llega el código de verificación en dos pasos y no puedo entrar a mi cuenta desde ayer.
Cuentas y accesos | 1 | 1 | Solicito un alias de correo adicional para recibir mensajes de mi línea de investigación.
Cuentas y accesos | 3 | 1 | Alguien intentó entrar a mi cuenta y ahora no puedo ingresar, necesito recuperarla ya para cerrar un trámite.
Cuentas y accesos | 2 | 2 | Dos docentes cambiaron de área y todavía conservan permisos de la anterior, hay que actualizarlos.
Cuentas y accesos | 1 | 1 | Mi foto de perfil institucional salió con otro nombre, favor de corregir cuando puedan.
Cuentas y accesos | 3 | 3 | Varias cuentas de profesores enviaron correos falsos de phishing, hay que bloquearlas hoy mismo.
Cuentas y accesos | 2 | 1 | Mi contraseña expiró y el sistema no me deja cambiarla, marca error al guardar.
Cuentas y accesos | 1 | 2 | Los permisos de la carpeta compartida del laboratorio están desordenados, aunque todos pueden trabajar.
Cuentas y accesos | 2 | 3 | Los alumnos de primer semestre no pueden activar su cuenta institucional con la liga que se les envió.
Cuentas y accesos | 3 | 2 | El jefe de grupo y la coordinadora no pueden entrar al sistema para firmar las actas que vencen hoy.
Cuentas y accesos | 2 | 2 | Necesito acceso de escritura a la carpeta del proyecto para mi equipo de cuatro personas, la entrega es la próxima semana.
Cuentas y accesos | 1 | 1 | ¿Cómo puedo actualizar el número de teléfono asociado a mi cuenta? Solo para tenerlo al día.
Cuentas y accesos | 3 | 1 | Me aparece «cuenta suspendida» al intentar entrar al sistema de calificaciones y el cierre es hoy.
Cuentas y accesos | 2 | 3 | Los permisos del grupo de docentes de ingeniería no se aplican y no ven el material del curso.
Cuentas y accesos | 1 | 2 | Se solicita revisar la lista de cuentas de exalumnos, hay algunas que parecen duplicadas.
Cuentas y accesos | 2 | 2 | El nuevo coordinador del laboratorio necesita permisos de administrador sobre las reservas.
Cuentas y accesos | 3 | 3 | El servidor de autenticación no responde y nadie en la facultad puede iniciar sesión en ningún sistema.
Cuentas y accesos | 1 | 3 | El texto del aviso de privacidad al iniciar sesión tiene un error tipográfico y lo ven todos los usuarios.
Cuentas y accesos | 2 | 1 | No puedo acceder a la carpeta de mi proyecto de tesis, dice que no tengo permisos desde el martes.
Cuentas y accesos | 3 | 2 | Hoy dieron de baja por error las cuentas de los instructores de un curso y las clases ya empezaron.
"""


def _leer(texto: str) -> tuple[tuple[str, int, int, str], ...]:
    ejemplos = []
    for linea in texto.strip().splitlines():
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        categoria, urgencia, impacto, descripcion = (
            parte.strip() for parte in linea.split("|", 3)
        )
        ejemplos.append((categoria, int(urgencia), int(impacto), descripcion))
    return tuple(ejemplos)


EJEMPLOS: tuple[tuple[str, int, int, str], ...] = _leer(_TEXTO)