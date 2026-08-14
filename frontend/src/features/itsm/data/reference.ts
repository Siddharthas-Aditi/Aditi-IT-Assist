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

export const LOCATIONS: LocationRef[] = [
  {
    id: 'loc-blr',
    name: 'India – Bangalore',
    country: 'India',
    city: 'Bangalore',
    timezone: 'Asia/Kolkata',
  },
  {
    id: 'loc-hyd',
    name: 'India – Hyderabad',
    country: 'India',
    city: 'Hyderabad',
    timezone: 'Asia/Kolkata',
  },
  {
    id: 'loc-pune',
    name: 'India – Pune',
    country: 'India',
    city: 'Pune',
    timezone: 'Asia/Kolkata',
  },
  {
    id: 'loc-dal',
    name: 'US – Dallas',
    country: 'United States',
    city: 'Dallas',
    timezone: 'America/Chicago',
  },
  {
    id: 'loc-nj',
    name: 'US – New Jersey',
    country: 'United States',
    city: 'Newark',
    timezone: 'America/New_York',
  },
  {
    id: 'loc-remote',
    name: 'Remote – Work From Home',
    country: '—',
    city: '—',
    timezone: '—',
  },
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
export const REGIONS = ['APAC', 'NAMER', 'EMEA'];
export const AVAILABILITY_ZONES = ['ap-south-1a', 'ap-south-1b', 'us-east-1a', 'on-premise'];
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
