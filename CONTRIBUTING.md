# Guía de contribución (S3-18)

Flujo de ramas, revisión de código y criterio de fusión del equipo SIGPI. Aplica desde el
Sprint 3 y se revisa en cada retrospectiva.

## 1. Una tarjeta, una rama, un pull request

1. Parte siempre de `main` actualizado:

   ```bash
   git switch main && git pull --rebase
   git switch -c feature/S3-13-pruebas-seguimiento
   ```

2. Nombre de la rama: `<tipo>/<tarjeta>-<descripcion-corta>`.

   | Tipo | Cuándo |
   | --- | --- |
   | `feature/` | Tarjeta de desarrollo (servidor, interfaz, integración, pruebas) |
   | `fix/` | Corrección de un defecto o de una observación de sprint |
   | `docs/` | Documentación, actas, registros |
   | `chore/` | CI, dependencias, configuración |

3. Un pull request por tarjeta (`S3-13`) o por observación (`Obs-4`). Si una tarjeta es
   grande, divídela en pull requests pequeños que se puedan revisar en menos de 30 minutos.
4. No se trabaja directamente sobre `main`.

## 2. Mensajes de commit

Formato `tipo(tarjeta): resumen en imperativo`, igual que el historial del Sprint 2, para
poder reconstruir la matriz de trazabilidad desde Git:

```text
feat(S3-01): agrega manejador global de errores
test(S3-06): prueba las nueve combinaciones de la matriz
fix(Obs-4): agrega PostgreSQL al trabajo de backend
docs(S3-18): documenta el flujo de ramas
```

El título del pull request lleva la tarjeta entre corchetes: `[S3-13] Pruebas de resolución`.

## 3. Antes de abrir el pull request

Desde la raíz del repositorio:

```bash
# Backend (con el entorno virtual activo)
cd backend
ruff check app tests alembic
ruff format --check app tests alembic
pytest

# Frontend
cd ../frontend
pnpm lint
pnpm format:check      # si falla: pnpm format
pnpm test
pnpm build
```

Si cambiaste la API, regenera los tipos del frontend:

```bash
cd backend && python -m scripts.export_openapi
cd ../frontend && pnpm generate:api
```

## 5. Revisión

- Cada pull request necesita **al menos una aprobación** de una persona distinta a la autora.
- Quien revisa responde en un día hábil. Si no puede, lo dice para reasignar la revisión.
- La autora no fusiona su propio pull request sin aprobación.
- Se revisa, en este orden: (1) cumple los criterios de aceptación de la historia;
  (2) respeta las capas (`api` → `services` → `domain`/`repositories`; el dominio no depende
  de frameworks); (3) tiene pruebas; (4) no expone secretos ni datos personales;
  (5) es legible. Los comentarios se resuelven antes de fusionar.
- Un cambio de esquema incluye su migración de Alembic y se revisa con
  `alembic upgrade head --sql`.

## 6. Criterio de fusión (Definition of Done)

Un pull request se fusiona con **squash** a `main` solo si:

- [ ] El pipeline de CI está en verde.
- [ ] La tarjeta de servidor o interfaz incluye sus pruebas automatizadas.
- [ ] Tiene la aprobación descrita en la sección 5.
- [ ] La documentación afectada (README, `docs/`, contrato de API) está actualizada.
- [ ] No incluye `.env`, credenciales, volcados de base de datos ni `node_modules`.

Después de fusionar se elimina la rama y se mueve la tarjeta a REALIZADO en el tablero.

## 7. Cobertura

Meta del proyecto: 60 % al cierre del Sprint 4 y 80 % al cierre del proyecto. Un pull request
no debe bajar la cobertura vigente.

## 8. Estado conocido del pipeline

El trabajo de backend de CI no tiene PostgreSQL, por lo que las dos pruebas de inalterabilidad
de la auditoría marcan error en GitHub aunque pasan en local (Documentación del Sprint 2,
observación 4). Hasta corregirlo, ese error conocido se anota en el pull request; no se
ignora ningún otro.
