# Reparto: delivery management for several businesses (PRD)

## Original request
"Quiero una app para gestionar el delivery de mis comercios"

User choices:
- Users: the owner and couriers.
- Businesses: several different businesses in one app.
- First version: orders, a product catalog with prices, and assigning and tracking couriers.
- Order list grouped by status, plus a map of couriers.
- Style: light and clean.

## Architecture
- **App:** Expo Router app, Spanish UI, sage-green colours, Plus Jakarta Sans font.
- **Server:** FastAPI with MongoDB (motor). Login uses JWT tokens and bcrypt-hashed passwords.
- **Owner:** logs in with email and password. Four tabs: Inicio, Órdenes, Mapa, Gestión. Native tabs are used on iOS 26+.
- **Courier:** logs in with phone and a 6-digit PIN. Has a single screen with large buttons.
- **Map:** react-native-maps on phones. The web preview shows a fallback list with Google Maps links.
- **Courier location:** expo-location, sent while the courier is online. It asks for permission first and offers Open Settings if the permission is blocked.

## Implemented (2026-06)
- **Accounts:** owner registration and login, courier login, and role-based access.
- **Businesses:** create and delete.
- **Product catalog:** add, delete, and switch availability.
- **Couriers:** create with phone and PIN, delete.
- **Orders:** create by typing the order amount and delivery fee (no product picker, changed 2026-06 at user request); total = amount + fee.
- **Order tracking:**
  - Status filters, a status timeline, and assign or change the courier.
  - Advance the status, or cancel the order.
  - Status changes follow fixed rules, and closed orders are locked.
- **Dashboard:** today's revenue and orders, couriers online, the order pipeline, businesses, and active orders.
- **Live map:** courier map, refreshed every 10 seconds.
- **Courier screen:**
  - Online switch with location sharing.
  - Current delivery, with "Salir en camino" (on the way) and "Marcar como entregado" (delivered).
  - Opens directions in the maps app and can call the customer.
- **Courier history and earnings (2026-06):**
  - New screen /courier-history with Día / Semana (Monday–Sunday) / Quincena (days 1–15 and 16–end) / Mes periods.
  - Pick any date from a calendar, or step back and forward one period at a time.
  - Shows total collected, delivery fees and number of deliveries, a per-day breakdown and the delivered orders.
  - The courier's home screen shows a "Hoy llevas" card for today.
  - Endpoint: GET /api/courier/history?start&end.
- **Currency:** euros everywhere, formatted as 1.234,50 €.
- **Order numbers:** come from an atomic counter, so two orders created at once can't share a number.
- **Payment, delivery proof, reports and route map (2026-06):**
  - Each order has a payment method: Ya pagado, Efectivo or Datáfono. It's set when creating the order and can be changed in the order detail.
  - The courier closes a delivery from a sheet where they can take an optional photo (stored in Emergent object storage) and write a note. The owner sees both in the order detail.
  - The courier's order card has a "Recoger" step with the business address and a navigation button, then an "Entregar" step.
  - Trip map with distinct icons for the courier, the business and the delivery point. Addresses are geocoded with OSM Nominatim (Spain, cached, at most 1 request per second).
  - Owner reports at /reports: Día / Semana / Quincena / Mes, any date, total revenue, totals by payment method, totals per courier (tap to filter the orders), a per-day breakdown, and all orders.
  - Courier totals now show only the sum of order totals; the separate delivery-fee figure is gone.
- **2026-06 update:**
  - Orders can be created without an amount (the amount field is optional).
  - On web the route map is a real OpenStreetMap map (Leaflet in an iframe) with icons for the courier, the business and the delivery point.
  - The courier sees the map on every active order, plus a visible hint and a 'Foto, nota y entregar' button.
- **Iteration 6 (2026-10):**
  - **Totals:** courier and owner totals now count only delivery fees.
  - **Payouts:** owner sees "Por pagar" per courier and a "Pagar" button that records the payout.
  - **Delivery photos:**
    - Uploads are verified on the server, and there's a backup base64 upload.
    - Empty uploads are rejected.
    - If a photo can't be loaded, a placeholder message shows instead.
  - **Address lookup:** Photon first, then Nominatim, biased to the business area, with abbreviation handling ("C." becomes "Calle").
  - **Courier alerts:** sound and vibration when a task is assigned or cancelled; only while the app is open (foreground polling).
  - **Navigation:** choice of Google Maps, Waze or Apple Maps.
  - **Timers:** courier timer since assignment (restarts on reassignment); owner timer since creation.
  - **Scheduled orders:** future date and time.
  - **Calls:** call-the-business button; emergency (SOS) phones set by the owner.
  - **Courier home:** today's delivered and cancelled tasks only.
  - **Full-screen map** with all of a courier's tasks.
  - **Sign-up disabled:** POST /auth/register returns 403.
  - **Spanish:** iOS locale set to Spanish.
- **Seed data:** 3 businesses, 2 couriers, and 5 orders.

## Backlog
- **P1**
  - Alerts to couriers when a new order is assigned.
  - Customer delivery-tracking link.
  - Map pins for order addresses.
  - Dashboard "today" in the local timezone.
- **P2**
  - Reports by business and courier.
  - Edit an order's products.
  - Courier earnings.
  - Mark couriers offline automatically after inactivity.
- **Builds:** Android production builds need a Google Maps API key for the map.
- **P0 pending (needs build or keys):**
  - Push notifications when the app is closed (Emergent push and google-services.json; works only in a built app).
  - Background location (expo-task-manager; dev or production build).
  - Google Maps provider with an API key for maps and geocoding.
- **P1 pending:**
  - Business user accounts (role "business": create tasks, assign to any courier or offer to all, see who accepted, no courier location).
  - Courier profile photo.
  - Courier "accept task" flow.
- **P2:** make the delivery photo mandatory (if the user wants it); use short-lived signed photo URLs; split server.py into modules.

## Iteration 7 (done)
- Business (comercio) role: owner creates email+password per business (business detail > "Acceso del comercio"). Login tab "Comercio" -> /biz screen. Business creates orders (/biz/orders) choosing a courier or "Libre" (open to all). Sees courier name, photo, phone, status, proof. NO courier location. Can cancel before pickup.
- Open tasks: couriers see "Tareas libres" and accept (atomic, first wins). Owner can also publish open orders.
- Courier profile photo (camera/gallery, object storage), shown to admin (manage list, order detail) and businesses.
- Push notifications (Emergent managed): register-push, sends on assign/open/accept/pickup/deliver/cancel. Works only in published build; google-services.json still pending from user.
- Background location via expo-task-manager (published build only), asked contextually.

## Iteration 8 (security audit fixes, done)
- Fixed blank app: duplicate `confirmDel` in business/[id].tsx.
- Admin password no longer reset on restart; demo business cafe@delivery.com removed.
- Change password (owner/business) with auth_version token revocation.
- Photo URLs use 30-min photo-only token (/api/photo-token); session JWT never in URLs.
- Uploads validated by magic bytes; served with nosniff + CSP.
- Login lockout: 5 fails -> 15 min (atomic $inc).
- Backlog: CORS restrict to known origins; rotate JWT secret at deploy.

## Iteration 9 (address/map/business improvements)
- Courier home: map always visible at top with all active + open tasks (own pin shown only if near the tasks). Per-order maps removed; full-screen map button kept for 2+ tasks.
- Owner sees "Entregado en X min desde que lo recogió" (pickup -> delivered) on order detail and OrderCard.
- Business: date+time shown on every card; full history with filter (Todos/Día/Semana/Quincena/Mes + calendar) via /api/biz/orders?start&end; business photo (/api/biz/photo, /api/businesses/{bid}/photo) shown to admin and couriers.
- Businesses never see delivery_fee/total (excluded server-side). Fee for business orders = Business.default_fee (set by owner); owner can edit per order (PATCH /api/orders/{id}/fee).
- Address suggestions dropdown (AddressInput) for delivery and pickup addresses: /api/places/autocomplete (Google Places if GOOGLE_MAPS_API_KEY set, else OpenStreetMap Photon) + /api/places/details. Picked coordinates saved exactly (dest_lat/lng, business lat/lng).
- Server always-on: requires deploying (preview sleeps).

## Iteration 10 (control tower & amounts)
- Owner OrderCard shows "Envío" and "Cobrar al cliente" (amount; "Ya pagado" if pagado) separately.
- Any user of the same owner can see every business photo.
- Address suggestions: up to 8, postcode-matching results first, 250ms debounce.
- Courier full-screen map also shows open (por aceptar) orders.
- Owner "Torre de control" map (tab Mapa): all couriers + all active orders (pickup/delivery) with courier name in titles; filter Todos / Sin repartidor / per courier. Uses GET /api/orders?active=true. Old CourierMap component deleted.
- Courier "Entregadas hoy" and history rows show business, address and delivery time.

## Iteration 11 (payment default + every Madrid portal)
- Orders with no amount to collect are saved as payment_method "pagado" (forced in backend build_order; the frontend shows only "Pagado" plus a hint when the amount is empty).
- Address suggestions now come first from CartoCiudad (the official IGN/Catastro address register, free, every portal): Madrid city first, then the Comunidad de Madrid; a typed postcode filters by cod_postal; then Photon and Nominatim as fallbacks. Also used by geocode() for typed (not picked) addresses. Geocode cache key changed to v3.

## Iteration 12 (multi-admin, km pricing, ranges, incidents, zoom, phones)
- Main admin = pedidosconustedes@gmail.com. Secondary admins (/api/admins, main only): linked (owner_user swaps id -> main tenant; cannot create courier/business accounts: account_admin dep) or independent (own tenant).
- Business distance pricing: pricing_mode km: km_base_price covers km_base_km, + km_extra_price per extra km. Shortest road route: Google Routes (if GOOGLE_MAPS_API_KEY) else OSRM, min over alternatives. Business orders auto-priced; owner gets quote (/api/businesses/{bid}/quote) prefilled. Order.distance_km.
- New orders default to "send to all online couriers" (open=true); push only to online couriers.
- Date ranges (Desde/Hasta): owner Órdenes (with summary), courier history ("Entre fechas"), business history.
- Courier incidents: POST /api/courier/orders/{id}/incident -> Order.incidents, shown in owner detail/card; notifies owner+business.
- Multiple named phones: Business.phones [{name,phone}], emergency_phones [{name,phone}] (PhonesEditor).
- Zoomable photos (ImageViewer): Avatar, BizPhoto, DeliveryPhoto.

## Iteration 13 (real road km + address edit)
- route_km: Google Routes API computeRoutes (DRIVE, vehicleStopover, alternatives) + an avoidHighways variant in parallel; bills the SHORTEST distance. Legacy Directions/DistanceMatrix/Geocoding are disabled on the key. OSRM fallback.
- google_geocode uses Places API (New) searchText; geocode cache key g2. places/details requests languageCode=es.
- Address edit for active orders: owner /order/[id] and business /biz-order/[id] (EditAddressSheet) -> PATCH /api/orders/{id}/address, /api/biz/orders/{id}/address; re-prices km/fee/total unless courier paid; 400 if address not found or order closed.
- Business detail shows fee + km + courier incidents. Órdenes range picker (status counts hidden in range mode).

## Iteration 14
- Reportes: "Entre fechas" chip with RangePicker (Desde/Hasta).
- GET /api/biz/quote?lat&lng (business): live fee + km shown in new-order form as soon as an address is picked (testID biz-quote); footer total includes the fee.
