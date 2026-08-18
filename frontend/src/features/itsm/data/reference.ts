/** Lookup lists backing every dropdown in the Change and Asset modules. */

import type { AssetTypeRef, LocationRef, Person, VendorRef } from './types';

export const WORKSPACES = ['IT Operations', 'Shared Services', 'Corporate IT'];

export const DEPARTMENTS = [
  'Shared Services – IT & Infrastructure',
  'Engineering',
  'Finance',
  'Human Resources',
  'Sales',
  'Customer Success',
  'Security & Compliance',
];

export const CATEGORIES = [
  'Network',
  'Server',
  'Security',
  'End User Computing',
  'Cloud',
  'Application',
  'Database',
  'Facilities',
];

export const GROUPS = [
  'IT Team',
  'Network Operations',
  'Infrastructure',
  'Security Operations',
  'Service Desk',
  'Cloud Platform',
];

export const MAINTENANCE_WINDOWS = [
  'Weekend – Sat 22:00 to Sun 04:00 IST',
  'Weeknight – 23:00 to 02:00 IST',
  'Monthly Patch Window – First Sunday',
  'Emergency – Immediate',
  'No Maintenance Window',
];

export const PEOPLE: Person[] = [
  {
    id: 'u-hareesh',
    name: 'Hareesh Kumar',
    email: 'hareesh@aditiconsulting.com',
    department: 'Shared Services – IT & Infrastructure',
  },
  {
    id: 'u-sagar',
    name: 'Sagar J',
    email: 'sagar@aditiconsulting.com',
    department: 'Shared Services – IT & Infrastructure',
  },
  {
    id: 'u-madhukar',
    name: 'Madhukar Rao',
    email: 'madhukar@aditiconsulting.com',
    department: 'Shared Services – IT & Infrastructure',
  },
  {
    id: 'u-siddhartha',
    name: 'Siddhartha Menon',
    email: 'siddhartha@aditiconsulting.com',
    department: 'Engineering',
  },
  {
    id: 'u-naresh',
    name: 'Naresh Iyer',
    email: 'naresh@aditiconsulting.com',
    department: 'Sales',
  },
  {
    id: 'u-priya',
    name: 'Priya Nair',
    email: 'priya@aditiconsulting.com',
    department: 'Finance',
  },
  {
    id: 'u-arjun',
    name: 'Arjun Desai',
    email: 'arjun@aditiconsulting.com',
    department: 'Security & Compliance',
  },
  {
    id: 'u-meera',
    name: 'Meera Krishnan',
    email: 'meera@aditiconsulting.com',
    department: 'Human Resources',
  },
  {
    id: 'u-rahul',
    name: 'Rahul Sharma',
    email: 'rahul@aditiconsulting.com',
    department: 'Engineering',
  },
  {
    id: 'u-anita',
    name: 'Anita Rao',
    email: 'anita@aditiconsulting.com',
    department: 'Customer Success',
  },
];

export function personName(id: string | null | undefined): string {
  if (!id) return '—';
  return PEOPLE.find((p) => p.id === id)?.name ?? id;
}

export const ASSET_TYPES: AssetTypeRef[] = [
  {
    id: 'at-ap',
    name: 'Access Point',
    category: 'Network',
    description: 'Wireless access points providing Wi-Fi coverage across offices.',
  },
  {
    id: 'at-laptop',
    name: 'Laptop',
    category: 'End User Computing',
    description: 'Employee-issued portable workstations.',
  },
  {
    id: 'at-monitor',
    name: 'Monitor',
    category: 'End User Computing',
    description: 'External displays issued with desk setups.',
  },
  {
    id: 'at-headset',
    name: 'Headset',
    category: 'End User Computing',
    description: 'Audio peripherals for support and sales teams.',
  },
  {
    id: 'at-firewall',
    name: 'Firewall',
    category: 'Network',
    description: 'Perimeter and internal segmentation firewalls.',
  },
  {
    id: 'at-mobile',
    name: 'Mobile Device',
    category: 'End User Computing',
    description: 'Corporate-issued phones and tablets.',
  },
  {
    id: 'at-switch',
    name: 'Switch',
    category: 'Network',
    description: 'Access and distribution layer network switches.',
  },
  {
    id: 'at-server',
    name: 'Server',
    category: 'Server',
    description: 'Physical and virtual compute hosts.',
  },
];

/**
 * Aditi's operating locations, as used by the business.
 *
 * Names are stored verbatim so they match the source system exactly — that
 * includes entries which look redundant to an outsider ("Raleigh" alongside
 * "USA - Raleigh", "Rep. Dominicana" alongside "Dominican Republic"). They are
 * distinct records in the business list, so they stay distinct here; the
 * Locations page can merge or remove any of them.
 */
export const SEED_LOCATIONS: LocationRef[] = [
  { id: 'loc-ar', name: 'Argentina', country: 'Argentina', city: '—', timezone: 'America/Argentina/Buenos_Aires' },
  { id: 'loc-bo', name: 'Bolivia', country: 'Bolivia', city: '—', timezone: 'America/La_Paz' },
  { id: 'loc-br', name: 'Brazil', country: 'Brazil', city: '—', timezone: 'America/Sao_Paulo' },
  { id: 'loc-ca', name: 'Canada', country: 'Canada', city: '—', timezone: 'America/Toronto' },
  { id: 'loc-cl', name: 'Chile', country: 'Chile', city: '—', timezone: 'America/Santiago' },
  { id: 'loc-cin', name: 'Cincinnati', country: 'USA', city: 'Cincinnati', timezone: 'America/New_York' },
  { id: 'loc-co', name: 'Colombia', country: 'Colombia', city: '—', timezone: 'America/Bogota' },
  { id: 'loc-cr', name: 'Costa Rica', country: 'Costa Rica', city: '—', timezone: 'America/Costa_Rica' },
  { id: 'loc-do', name: 'Dominican Republic', country: 'Dominican Republic', city: '—', timezone: 'America/Santo_Domingo' },
  { id: 'loc-ec', name: 'Ecuador', country: 'Ecuador', city: '—', timezone: 'America/Guayaquil' },
  { id: 'loc-sv', name: 'El Salvador', country: 'El Salvador', city: '—', timezone: 'America/El_Salvador' },
  { id: 'loc-eu', name: 'Europe', country: 'Europe', city: '—', timezone: 'Europe/London' },
  { id: 'loc-gt', name: 'Guatemala', country: 'Guatemala', city: '—', timezone: 'America/Guatemala' },
  { id: 'loc-hn', name: 'Honduras', country: 'Honduras', city: '—', timezone: 'America/Tegucigalpa' },
  { id: 'loc-in', name: 'India', country: 'India', city: '—', timezone: 'Asia/Kolkata' },
  { id: 'loc-in-blr', name: 'India - Bangalore', country: 'India', city: 'Bangalore', timezone: 'Asia/Kolkata' },
  { id: 'loc-in-con', name: 'India - Consultant', country: 'India', city: '—', timezone: 'Asia/Kolkata' },
  { id: 'loc-in-vad', name: 'India - Vadodara', country: 'India', city: 'Vadodara', timezone: 'Asia/Kolkata' },
  { id: 'loc-jm', name: 'Jamaica', country: 'Jamaica', city: '—', timezone: 'America/Jamaica' },
  { id: 'loc-mx', name: 'Mexico', country: 'Mexico', city: '—', timezone: 'America/Mexico_City' },
  { id: 'loc-py', name: 'Paraguay', country: 'Paraguay', city: '—', timezone: 'America/Asuncion' },
  { id: 'loc-pe', name: 'Peru', country: 'Peru', city: '—', timezone: 'America/Lima' },
  { id: 'loc-ral', name: 'Raleigh', country: 'USA', city: 'Raleigh', timezone: 'America/New_York' },
  { id: 'loc-repdo', name: 'Rep. Dominicana', country: 'Dominican Republic', city: '—', timezone: 'America/Santo_Domingo' },
  { id: 'loc-es', name: 'Spain', country: 'Spain', city: '—', timezone: 'Europe/Madrid' },
  { id: 'loc-uy', name: 'Uruguay', country: 'Uruguay', city: '—', timezone: 'America/Montevideo' },
  { id: 'loc-us', name: 'USA', country: 'USA', city: '—', timezone: 'America/New_York' },
  { id: 'loc-us-bel', name: 'USA - Bellevue', country: 'USA', city: 'Bellevue', timezone: 'America/Los_Angeles' },
  { id: 'loc-us-cal', name: 'USA - California', country: 'USA', city: '—', timezone: 'America/Los_Angeles' },
  { id: 'loc-us-con', name: 'USA - Consultant', country: 'USA', city: '—', timezone: 'America/New_York' },
  { id: 'loc-us-ral', name: 'USA - Raleigh', country: 'USA', city: 'Raleigh', timezone: 'America/New_York' },
];

export const VENDORS: VendorRef[] = [
  {
    id: 'v-blr4u',
    name: 'BLR4U India',
    contactName: 'Ramesh Gupta',
    email: 'support@blr4u.in',
    phone: '+91 80 4123 8800',
    supportUrl: 'https://support.blr4u.in',
  },
  {
    id: 'v-dell',
    name: 'Dell Technologies',
    contactName: 'Karen Mills',
    email: 'enterprise@dell.com',
    phone: '+1 800 456 3355',
    supportUrl: 'https://dell.com/support',
  },
  {
    id: 'v-lenovo',
    name: 'Lenovo India',
    contactName: 'Sunil Bhat',
    email: 'b2b@lenovo.in',
    phone: '+91 80 4030 1200',
    supportUrl: 'https://support.lenovo.com',
  },
  {
    id: 'v-apple',
    name: 'Apple Distribution',
    contactName: 'Jonathan Reeve',
    email: 'business@apple.com',
    phone: '+1 800 692 7753',
    supportUrl: 'https://support.apple.com/business',
  },
  {
    id: 'v-fortinet',
    name: 'Fortinet',
    contactName: 'Wei Chen',
    email: 'support@fortinet.com',
    phone: '+1 866 868 3678',
    supportUrl: 'https://support.fortinet.com',
  },
  {
    id: 'v-jabra',
    name: 'Jabra Business',
    contactName: 'Lise Andersen',
    email: 'orders@jabra.com',
    phone: '+45 72 20 60 00',
    supportUrl: 'https://jabra.com/support',
  },
  {
    id: 'v-samsung',
    name: 'Samsung Enterprise',
    contactName: 'Ji-woo Park',
    email: 'b2b@samsung.com',
    phone: '+82 2 2255 0114',
    supportUrl: 'https://samsung.com/business/support',
  },
];

export const CLASSIFICATIONS = ['Internal', 'Confidential', 'Restricted', 'Public'];
/** Offered in the Locations form as suggestions — any other value is accepted. */
export const COUNTRIES = [
  'India',
  'USA',
  'Argentina',
  'Bolivia',
  'Brazil',
  'Canada',
  'Chile',
  'Colombia',
  'Costa Rica',
  'Dominican Republic',
  'Ecuador',
  'El Salvador',
  'Europe',
  'Guatemala',
  'Honduras',
  'Jamaica',
  'Mexico',
  'Paraguay',
  'Peru',
  'Spain',
  'Uruguay',
];
export const PHYSICAL_SUBTYPES = ['Access Point', 'Desktop', 'Laptop', 'Peripheral', 'Appliance', 'Rack Server'];
export const VIRTUAL_SUBTYPES = ['Virtual Machine', 'Container Host', 'Cloud Instance', 'Not Applicable'];
export const SOURCES = ['Manual', 'Discovery Scan', 'Intune Sync', 'CSV Import'];
export const CONTRACTS = [
  'AMC-2026-NETWORK',
  'AMC-2026-ENDPOINT',
  'AppleCare Enterprise 2026',
  'FortiCare 24x7',
  'No Contract',
];
