# Website - editing services

A one-page website that sells the editing work: services, caption styles,
prices, questions and an order form. Everything is in `index.html` (plus the
pictures in `img/`), so it works on any free website host.

## Change your details and prices

Open `index.html` in Notepad, scroll to the bottom and find `SETTINGS`:

- `brand` - your business name
- `whatsapp` - your WhatsApp number with the country code, only digits
- `email` - your business email
- `instagram` - your Instagram name without @
- `payments` - how people pay you (shown under "How do I pay?")
- `plans` and `extras` - names, prices and what each one includes

Save the file. Until you add WhatsApp, email or Instagram, the order section
shows a reminder instead of the send buttons.

## How orders work

The customer fills in the form and clicks **Write my order**. The site writes
the order as a message and shows **Send on WhatsApp** / **Send by email**
buttons (for the contacts you set) and **Copy message**. No server or
database needed.

## Put it online (free)

**Netlify Drop** (easiest, 2 minutes):
1. Go to https://app.netlify.com/drop
2. Drag the whole `website` folder onto the page.
3. You get a link like `https://something.netlify.app`. Make a free account
   to keep the site and to give it a nicer name or your own domain.

To update it later, drag the folder again in your site's **Deploys** page.

The sample pictures were made with Clip Factory's caption styles
(`renderer.preview_image`).
