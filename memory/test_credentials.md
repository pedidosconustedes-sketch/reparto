# Test Credentials

## Administrador principal (owner, main) - pestaña "Admin"
- Email: pedidosconustedes@gmail.com — this is the REAL USER's own account (id 6ae34bf6c4b986a63025ed26) with the user's own password (unknown to agents). DO NOT try to log in with guesses (5 failures lock it 15 min). Never change its password.
- Demo/seed admin for tests: admin@delivery.com / Admin12345 (id 6ae347236362b29c3e2fb5c8; also is_main=true since it has no parent). Use this one for automated tests.
- Unique index uniq_role_email prevents duplicate emails per role.
- Only the main admin sees Gestión > "Admins" tab and can create secondary admins (POST /api/admins {name,email,password,linked}).

## Administradores secundarios
- None seeded. Create via the API/UI as the main admin; linked=true -> works on the main account's data but cannot create courier/business accounts; linked=false -> independent tenant (own businesses/couriers). Delete after tests.

## Comercio (business)
- No demo account. Create via PUT /api/businesses/{bid}/account {email,password} as admin; log in on the "Comercio" tab. Delete afterwards.

## Repartidores (courier) - teléfono + PIN
- Carlos Gómez: 1100000001 / 123456
- Lucía Pérez: 1100000002 / 654321

## Login lockout
- 5 failed attempts -> 15 min lock (429). Clear failed_logins/locked_until in Mongo if a test locks an account.
